"""Verify channel isolation, FIFO behavior, and capture at the HTTP boundary."""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from test_workflow_catalog import API, API_MODULE, ChannelState, Plugin


class ChannelRecordTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="comfy-record-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "history_channels.json"
        self.plugin = Plugin.__new__(Plugin)
        self.plugin.channel_state = ChannelState(self.state_path)
        self.plugin.admin_user_ids = {"admin"}
        self.plugin.discard_prompt_from_history = True
        self.plugin._check_access = Mock(return_value=(True, ""))
        self.plugin._inject_draw_failure_context = Mock()
        self.plugin._clean_pic_tags_from_req = Mock()
        self.plugin.api = types.SimpleNamespace(url="http://comfy.example")

    def event(self, user="admin", group="group-1", platform="bot-1"):
        extra = {}
        return types.SimpleNamespace(
            unified_msg_origin=f"{platform}:GroupMessage:{group}_{user}",
            message_str="/comfy_history on",
            get_group_id=lambda: group,
            get_sender_id=lambda: user,
            get_extra=lambda key: extra.get(key),
            set_extra=lambda key, value: extra.__setitem__(key, value),
            plain_result=lambda message: message,
        )

    async def command(self, event, action):
        event.message_str = f"/comfy_history {action}"
        return [result async for result in self.plugin.cmd_comfy_history(event)]

    async def test_history_survives_new_conversation_restart_and_is_shared_in_group(self):
        event = self.event()
        self.assertIn("已开启", (await self.command(event, "on"))[0])
        # A different group member starts a fresh conversation with a different cid.
        member = self.event(user="member")
        req = types.SimpleNamespace(system_prompt="persona", conversation=types.SimpleNamespace(cid="new-cid"))
        await self.plugin.prepare_llm_request(member, req)
        self.plugin._clean_pic_tags_from_req.assert_not_called()
        self.assertEqual(req.system_prompt, "persona")
        self.plugin.channel_state = ChannelState(self.state_path)
        self.assertTrue(self.plugin._is_prompt_history_keep_active(member))
        self.assertFalse(self.plugin._is_prompt_history_keep_active(self.event(group="group-2")))
        self.assertFalse(self.plugin._is_prompt_history_keep_active(self.event(platform="bot-2")))
        self.assertFalse(self.plugin._is_prompt_history_keep_active(self.event(group="")))
        self.assertIn("已关闭", (await self.command(event, "off"))[0])
        await self.plugin.prepare_llm_request(member, req)
        self.plugin._clean_pic_tags_from_req.assert_called_once_with(req)
        self.assertFalse(ChannelState(self.state_path).keep_history(self.plugin._get_channel_key(event)))

    async def test_history_private_channels_and_admin_requirement(self):
        event = self.event(group="")
        self.assertIn("已开启", (await self.command(event, "on"))[0])
        self.assertTrue(self.plugin._is_prompt_history_keep_active(self.event(group="")))
        self.assertFalse(self.plugin._is_prompt_history_keep_active(self.event(group="", user="someone")))
        self.assertIn("权限不足", (await self.command(self.event(user="member"), "off"))[0])
        self.assertTrue(self.plugin._is_prompt_history_keep_active(event))
        self.plugin.discard_prompt_from_history = False
        self.assertIn("已关闭", (await self.command(event, "off"))[0])
        self.assertIn("已开启", (await self.command(event, "on"))[0])

    async def test_queue_evicts_oldest_and_pops_fifo_without_crossing_channels(self):
        event = self.event()
        record = self.plugin._submission_recorder(event)
        payload = {"prompt": {"1": {"inputs": {"text": "full prompt"}}}, "client_id": "client"}
        for seed in range(22):
            payload["prompt"]["1"]["inputs"]["seed"] = seed
            record("example.json", payload)
        payload["prompt"].clear()
        response = json.loads(await self.plugin.comfy_record(self.event(user="member")))
        self.assertEqual(response["remaining"], 20)
        self.assertEqual([item["request"]["prompt"]["1"]["inputs"]["seed"] for item in response["records"]], list(range(2, 22)))
        for other in [self.event(group="other"), self.event(platform="bot-2"), self.event(group="")]:
            self.assertEqual(json.loads(await self.plugin.comfy_record(other))["records"], [])
        popped = json.loads(await self.plugin.comfy_record(event, "pop", 2))
        self.assertEqual([item["request"]["prompt"]["1"]["inputs"]["seed"] for item in popped["records"]], [2, 3])
        self.assertEqual(popped["remaining"], 18)
        remaining = json.loads(await self.plugin.comfy_record(event))
        self.assertEqual(remaining["records"][0]["request"]["prompt"]["1"]["inputs"]["seed"], 4)
        self.assertEqual(json.loads(await self.plugin.comfy_record(event, "pop", 20))["remaining"], 0)
        self.assertEqual(json.loads(await self.plugin.comfy_record(event, "pop"))["records"], [])

    async def test_record_validation_and_access_never_consume_queue(self):
        event = self.event()
        self.plugin._submission_recorder(event)("example.json", {"prompt": {}, "client_id": "1"})
        for action, count in [("bad", 1), ("pop", 0), ("pop", 21), ("pop", True), ("pop", "1")]:
            self.assertIn("error", json.loads(await self.plugin.comfy_record(event, action, count)))
        self.plugin._check_access.return_value = (False, "access denied")
        self.assertEqual(await self.plugin.comfy_record(event, "pop"), "access denied")
        self.assertEqual(self.plugin.channel_state.record_count(self.plugin._get_channel_key(event)), 1)

    async def test_records_exact_final_payload_and_rejected_http_attempts(self):
        directory = Path(self.tmp.name) / "workflow"
        directory.mkdir()
        graph = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "template positive"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "template negative"}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 12}},
            "4": {"class_type": "Lora Loader (LoraManager)", "inputs": {
                "loras": {"__value__": [{"name": "character.safetensors", "active": False}]},
            }},
        }
        (directory / "example.json").write_text(json.dumps(graph), encoding="utf-8")
        api = API({
            "workflow_settings": {"json_file": "example.json", "input_node_id": "1", "neg_node_id": "2"},
            "sub_config": {"negative_prompt": "default negative"},
            "llm_settings": {"lora_control": {"enabled": True}},
        }, Path(self.tmp.name))
        self.plugin.api = api
        event = self.event()
        response = types.SimpleNamespace(status=200, json=AsyncMock(return_value={"prompt_id": "accepted"}))
        response_context = MagicMock()
        response_context.__aenter__.return_value = response
        session = types.SimpleNamespace(post=Mock(return_value=response_context))
        session_context = MagicMock()
        session_context.__aenter__.return_value = session
        api.wait_for_result = AsyncMock(return_value=(b"image", None))
        with patch.object(API_MODULE.aiohttp, "ClientSession", return_value=session_context, create=True), patch.object(
            api, "resolve_lora_selections", return_value=[{
                "name": "character.safetensors", "strength": 0.8, "clip_strength": 0.6,
                "selected_prompt_hints": ["trigger"],
            }],
        ):
            result = await api.generate("用户的完整画面", lora_selections=[{"name": "character.safetensors"}],
                                        negative_prompt="explicit negative", on_submit=self.plugin._submission_recorder(event))
            self.assertEqual(result, (b"image", None))
            sent = session.post.call_args.kwargs["json"]
            records = json.loads(await self.plugin.comfy_record(event))["records"]
            self.assertEqual(records[0]["request"], sent)
            self.assertEqual(records[0]["workflow"], "example.json")
            self.assertEqual(sent["prompt"]["1"]["inputs"]["text"], "trigger, 用户的完整画面")
            self.assertEqual(sent["prompt"]["2"]["inputs"]["text"], "template negative, default negative, explicit negative")
            self.assertNotEqual(sent["prompt"]["3"]["inputs"]["seed"], 0)
            selected_lora = sent["prompt"]["4"]["inputs"]["loras"]["__value__"][0]
            self.assertTrue(selected_lora["active"])
            self.assertEqual(selected_lora["strength"], "0.8")
            self.assertEqual(selected_lora["clipStrength"], "0.6")
            response.status = 400
            response.reason = "Bad request"
            response.text = AsyncMock(return_value='{"error": "rejected"}')
            prompt_id, error = await api.submit("another", on_submit=self.plugin._submission_recorder(event))
            self.assertIsNone(prompt_id)
            self.assertIn("400", error)
            self.assertEqual(json.loads(await self.plugin.comfy_record(event))["remaining"], 2)
            await api.submit("not sent", workflow_filename="missing.json", on_submit=self.plugin._submission_recorder(event))
            self.assertEqual(json.loads(await self.plugin.comfy_record(event))["remaining"], 2)

    async def test_repeated_batch_records_each_submission_for_its_channel(self):
        event = self.event()

        async def submit(prompt, **kwargs):
            kwargs["on_submit"]("example.json", {"prompt": {"text": prompt}, "client_id": "batch"})
            return "accepted", None

        self.plugin.api.submit = submit
        results = await self.plugin._submit_repeated_batch(event, "batch prompt", 3)
        self.assertEqual(len(results), 3)
        self.assertEqual(json.loads(await self.plugin.comfy_record(event))["remaining"], 3)


if __name__ == "__main__":
    unittest.main()
