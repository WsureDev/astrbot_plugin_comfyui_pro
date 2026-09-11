import unittest

from workflow_info import inspect_workflow_models


class WorkflowInfoTests(unittest.TestCase):
    def test_reports_static_loader_models_and_enabled_lora(self):
        result = inspect_workflow_models({
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "diffusion.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "encoder.safetensors", "type": "custom"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
            "4": {"class_type": "Lora Loader (LoraManager)", "inputs": {
                "loras": {"__value__": [
                    {"name": "enabled.safetensors", "active": True},
                    {"name": "disabled.safetensors", "active": False},
                ]},
            }},
        })
        files = {(item["role"], item["filename"]) for item in result["models"]}
        self.assertIn(("diffusion", "diffusion.safetensors"), files)
        self.assertIn(("text_encoder", "encoder.safetensors"), files)
        self.assertIn(("vae", "vae.safetensors"), files)
        self.assertIn(("lora", "enabled.safetensors"), files)
        self.assertEqual(result["inactive_lora_count"], 1)

    def test_keeps_dynamic_inputs_unresolved_instead_of_guessing(self):
        result = inspect_workflow_models({
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": ["node", 0]}},
            "2": {"class_type": "CustomModelLoader", "inputs": {"model": "runtime"}},
        })
        self.assertEqual(result["unresolved_inputs"][0]["link"], ["node", 0])
        self.assertEqual(result["unrecognized_loaders"][0]["class_type"], "CustomModelLoader")

    def test_rejects_non_api_graph(self):
        with self.assertRaises(ValueError):
            inspect_workflow_models({"nodes": []})


if __name__ == "__main__":
    unittest.main()
