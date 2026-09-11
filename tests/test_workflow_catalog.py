"""Exercise real plugin methods with AstrBot and HTTP imports stubbed out."""
import importlib
import json
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    def decorator(*args, **kwargs):
        return lambda function: function

    names = [
        "astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.star",
        "astrbot.api.message_components", "astrbot.api.provider", "astrbot.core",
        "astrbot.core.message", "astrbot.core.message.message_event_result", "aiohttp", "requests",
    ]
    modules = {name: types.ModuleType(name) for name in names}
    modules["astrbot.api"].logger = logging.getLogger("test_comfy")
    modules["astrbot.api"].llm_tool = decorator
    event = modules["astrbot.api.event"]
    event.filter = types.SimpleNamespace(**{name: decorator for name in (
        "command", "on_llm_request", "on_llm_response", "on_decorating_result", "after_message_sent",
    )})
    event.AstrMessageEvent = event.MessageEventResult = event.ResultContentType = object
    star = modules["astrbot.api.star"]
    star.Context = star.Star = star.StarTools = object
    star.register = decorator
    modules["astrbot.api.provider"].LLMResponse = object
    modules["astrbot.core.message.message_event_result"].MessageChain = object
    package = types.ModuleType("_comfy_test")
    package.__path__ = [str(ROOT)]
    modules[package.__name__] = package
    with patch.dict(sys.modules, modules):
        main = importlib.import_module("_comfy_test.main")
        api = importlib.import_module("_comfy_test.comfyui_api")
    return main.ComfyUIPlugin, api.ComfyUI


Plugin, API = load_plugin()


class WorkflowCatalogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name) / "workflow"
        directory.mkdir()
        for filename, model in [("default.json", "default.ckpt"), ("other.json", "other.ckpt")]:
            (directory / filename).write_text(json.dumps({
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
            }), encoding="utf-8")
        (directory / "other.lora.json").write_text("{}", encoding="utf-8")
        (directory / "broken.json").write_text("{bad json", encoding="utf-8")
        self.api = API({}, Path(self.tmp.name))
        self.api.wf_filename = "default.json"
        self.api.workflow_path = directory / "default.json"
        self.plugin = Plugin.__new__(Plugin)
        self.plugin.api = self.api
        self.plugin.workflow_dir = directory
        self.plugin.config = {"llm_settings": {"system_prompt": "用户补充流程", "environment_prompt": "实例自定义模型资料"}}
        self.plugin.lora_control_enabled = False
        self.plugin.discard_prompt_from_history = False
        self.plugin._check_access = Mock(return_value=(True, ""))
        self.plugin._inject_draw_failure_context = Mock()
        extra = {}
        self.event = types.SimpleNamespace(
            get_extra=lambda key: extra.get(key), set_extra=lambda key, value: extra.__setitem__(key, value),
            unified_msg_origin="test",
        )

    async def test_query_selects_requested_graph_without_switching_default(self):
        response = json.loads(await self.plugin.comfyui_workflows(self.event, "OTHER"))
        self.assertEqual(response["workflows"][0]["models"][0]["filename"], "other.ckpt")
        self.assertFalse(response["workflows"][0]["is_default"])
        self.assertEqual(self.api.wf_filename, "default.json")
        self.assertEqual(response["environment_notes"], "实例自定义模型资料")
        missing = json.loads(await self.plugin.comfyui_workflows(self.event, "missing"))
        self.assertIn("error", missing)

    async def test_list_isolates_invalid_workflow_and_excludes_sidecars(self):
        response = json.loads(await self.plugin.comfyui_workflows(self.event))
        entries = {entry["workflow"]: entry for entry in response["workflows"]}
        self.assertEqual(set(entries), {"broken.json", "default.json", "other.json"})
        self.assertIn("error", entries["broken.json"])
        self.assertEqual(entries["default.json"]["models"][0]["filename"], "default.ckpt")
        self.plugin._check_access.return_value = (False, "access denied")
        self.assertEqual(await self.plugin.comfyui_workflows(self.event), "access denied")

    async def test_system_prompt_preserves_persona_and_exposes_model_evidence(self):
        persona = "本轮用用户指定的工具资料，保持我的语言及构图习惯。"
        req = types.SimpleNamespace(system_prompt=persona)
        await self.plugin.inject_system_prompt(self.event, req)
        self.assertTrue(req.system_prompt.startswith(persona))
        self.assertIn("other.ckpt", req.system_prompt)
        self.assertIn("实例自定义模型资料", req.system_prompt)
        self.assertIn("用户补充流程", req.system_prompt)
        self.assertEqual(self.event.get_extra("comfy_user_system_prompt"), persona)
        await self.plugin.inject_system_prompt(self.event, req)
        self.assertEqual(req.system_prompt.count("用户补充流程"), 1)

    async def test_supplemental_request_retains_incoming_persona(self):
        self.plugin.force_draw_when_no_prompt = True
        self.plugin.target_image_count = 1
        self.plugin._build_force_draw_contexts = Mock(return_value=[])
        provider = types.SimpleNamespace(text_chat=AsyncMock(return_value=types.SimpleNamespace(
            completion_text='<pic prompt="用户选择的画面描述">',
        )))
        self.plugin.context = types.SimpleNamespace(
            get_using_provider=lambda origin: provider,
            conversation_manager=types.SimpleNamespace(get_curr_conversation_id=AsyncMock(return_value=None)),
        )
        await self.plugin.inject_system_prompt(self.event, types.SimpleNamespace(system_prompt="人格提供的提示词编写规则"))
        results = await self.plugin._generate_force_draw_prompt_entries(self.event, "这是本轮用户要求的画面。" * 20)
        self.assertEqual(len(results), 1)
        self.assertIn("人格提供的提示词编写规则", provider.text_chat.call_args.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
