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

    async def test_system_prompt_preserves_persona_without_loading_catalogs(self):
        persona = "本轮用用户指定的工具资料，保持我的语言及构图习惯。"
        self.plugin.lora_control_enabled = True
        self.plugin.config["llm_settings"]["lora_control"] = {
            "enabled": True, "inject_catalog_into_system_prompt": True,
        }
        self.plugin._get_workflow_catalog = Mock(side_effect=AssertionError("unexpected workflow read"))
        self.api.get_lora_prompt_appendix = Mock(side_effect=AssertionError("unexpected appendix read"))
        req = types.SimpleNamespace(system_prompt=persona)
        await self.plugin.inject_system_prompt(self.event, req)
        self.assertTrue(req.system_prompt.startswith(persona))
        self.assertIn("comfyui_usage", req.system_prompt)
        self.assertIn("comfyui_workflows", req.system_prompt)
        self.assertIn("default.json", req.system_prompt)
        self.assertNotIn("other.ckpt", req.system_prompt)
        self.assertNotIn("实例自定义模型资料", req.system_prompt)
        self.assertIn("用户补充流程", req.system_prompt)
        self.assertLess(len(req.system_prompt), 1000)
        self.assertEqual(self.event.get_extra("comfy_user_system_prompt"), persona)
        await self.plugin.inject_system_prompt(self.event, req)
        self.assertEqual(req.system_prompt.count("用户补充流程"), 1)
        self.plugin._get_workflow_catalog.assert_not_called()
        self.api.get_lora_prompt_appendix.assert_not_called()

    async def test_usage_returns_packaged_docs_and_effective_settings_without_scanning(self):
        self.api.lora_control_enabled = True
        self.api.max_lora_count = 2
        self.api.inject_selected_lora_hints = False
        self.api.keep_workflow_defaults_when_selected = False
        self.api._scan_lora_catalog = Mock(side_effect=AssertionError("unexpected inventory scan"))
        self.api._load_workflow = Mock(side_effect=AssertionError("unexpected workflow read"))
        before = json.dumps(self.plugin.config, sort_keys=True)
        response = await self.plugin.comfyui_usage(self.event)
        runtime = json.loads(response.splitlines()[1])
        self.assertEqual(runtime["default_workflow"], "default.json")
        self.assertTrue(runtime["lora_control_enabled"])
        self.assertEqual(runtime["max_lora_count"], 2)
        self.assertFalse(runtime["inject_selected_prompt_hints"])
        self.assertFalse(runtime["keep_workflow_defaults_when_selected"])
        self.assertFalse(runtime["catalog_in_system_prompt"])
        self.assertTrue(response.endswith((ROOT / "docs" / "comfyui_txt2img_tool.md").read_text(encoding="utf-8")))
        self.assertIn("search_local_inventory", response)
        self.assertIn("negative_prompt", response)
        self.assertEqual(before, json.dumps(self.plugin.config, sort_keys=True))
        self.api._scan_lora_catalog.assert_not_called()
        self.api._load_workflow.assert_not_called()

    def test_previous_builtin_prompt_upgrades_without_rewriting_custom_settings(self):
        previous = (
            "【画图提示词编写助手】\n根据用户当前的画图需求编写提示词，并使用 ComfyUI 工具生成图片。\n\n"
            "1. 先查看上下文提供的 workflow 与模型声明；信息不足时调用 comfyui_workflows 查询。用户未指定 workflow 时使用默认值，指定时从可用列表中选择。\n"
            "2. 提示词语言、形式、风格和提示词 MCP/skill 的使用建议，遵循用户的人格/系统提示词和本次要求，结合目标模型资料决定。插件不预设标签、自然语言或特定风格，也不绑定某个外部工具。\n"
            "3. 只能使用本轮实际可用且符合用户指导的 MCP/skill。模型文件名或编码器类型不能单独证明提示词语法、权重或负面词支持；不确定时查询用户指定的资料或询问用户，不编造推荐。\n"
            "4. 生成图片时调用 comfyui_txt2img，正向描述放 prompt，负面描述放 negative_prompt。工具调用不使用聊天命令的选项语法；以工具真实结果说明状态。批量已提交时由插件继续等待，不重复提交。\n"
            "5. 用户没有要求出图时不主动提交生成任务。实例模型说明和可用工具经验由用户配置提供，不能将其视作所有模型的通用规则。"
        )
        self.plugin.config["llm_settings"]["system_prompt"] = previous
        self.assertTrue(self.plugin._get_comfy_system_prompt().startswith("【ComfyUI 使用约定】"))
        self.assertEqual(self.plugin.config["llm_settings"]["system_prompt"], previous)
        custom = previous + "\n额外用户约定必须保留。"
        self.plugin.config["llm_settings"]["system_prompt"] = custom
        self.assertTrue(self.plugin._get_comfy_system_prompt().startswith(custom))

    async def test_usage_checks_access_and_reports_missing_document(self):
        self.plugin._check_access.return_value = (False, "access denied")
        with patch.object(Path, "read_text", side_effect=FileNotFoundError) as read:
            self.assertEqual(await self.plugin.comfyui_usage(self.event), "access denied")
            read.assert_not_called()
            self.plugin._check_access.return_value = (True, "")
            self.assertIn("使用说明文件缺失或不可读", await self.plugin.comfyui_usage(self.event))

    async def test_usage_remains_available_without_initialized_api(self):
        self.plugin.api = None
        response = await self.plugin.comfyui_usage(self.event)
        runtime = json.loads(response.splitlines()[1])
        self.assertFalse(runtime["api_initialized"])
        self.assertFalse(runtime["lora_control_enabled"])
        self.assertIsNone(runtime["default_workflow"])
        self.assertIn("negative_prompt", response)

    async def test_initialize_activates_usage_with_existing_tools(self):
        self.plugin.context = types.SimpleNamespace(activate_llm_tool=Mock())
        self.plugin._auto_update_schema = Mock()
        self.plugin._watch_workflow_schema = AsyncMock()
        await self.plugin.initialize()
        await self.plugin._workflow_schema_watch_task
        activated = [call.args[0] for call in self.plugin.context.activate_llm_tool.call_args_list]
        self.assertEqual(set(activated), {"comfyui_usage", "comfyui_workflows", "comfyui_txt2img"})

    def test_saved_true_disables_appendix_but_preserves_lora_execution_and_exclusions(self):
        root = Path(self.tmp.name)
        lora_dir = root / "loras"
        lora_dir.mkdir()
        (lora_dir / "character.safetensors").write_bytes(b"test fixture, not a model")
        metadata_path = lora_dir / "character.metadata.json"
        metadata = {"model_name": "Fixture Character", "civitai": {"trainedWords": ["fixture_character"]}}
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        graph = {"23": {"class_type": "Lora Loader (LoraManager)", "inputs": {
            "loras": {"__value__": [{"name": "character.safetensors", "active": False}]},
        }}}
        (root / "workflow" / "default.json").write_text(json.dumps(graph), encoding="utf-8")
        config = {
            "workflow_settings": {"json_file": "default.json"},
            "llm_settings": {"lora_control": {
                "enabled": True, "inject_catalog_into_system_prompt": True,
                "scan_directories": str(lora_dir), "inject_selected_prompt_hints": True,
            }},
        }
        api = API(config, root)
        self.assertFalse(api.inject_lora_catalog)
        with patch.object(api, "get_lora_runtime_context", side_effect=AssertionError("unexpected inventory scan")):
            self.assertEqual(api.get_lora_prompt_appendix(), "")
        selections = api.resolve_lora_selections([{"name": "character.safetensors", "strength": 0.8}])
        self.assertEqual(len(selections), 1)
        self.assertEqual(selections[0]["selected_prompt_hints"], ["fixture_character"])
        prompt, hints = api._inject_selected_lora_prompt_hints("standing", selections)
        self.assertEqual(prompt, "fixture_character, standing")
        self.assertEqual(hints, ["fixture_character"])
        self.assertTrue(api._apply_lora_selections(graph, selections))
        self.assertTrue(graph["23"]["inputs"]["loras"]["__value__"][0]["active"])
        metadata["exclude"] = True
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(api.resolve_lora_selections([{"name": "character.safetensors"}]), [])

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
        supplemental_prompt = provider.text_chat.call_args.kwargs["system_prompt"]
        self.assertIn("人格提供的提示词编写规则", supplemental_prompt)
        self.assertIn("default.ckpt", supplemental_prompt)
        self.assertIn("实例自定义模型资料", supplemental_prompt)
        self.assertNotIn("other.ckpt", supplemental_prompt)


if __name__ == "__main__":
    unittest.main()
