"""Read model selections from API graphs without executing nodes or guessing prompt styles."""

# These are node input contracts, not model-family or prompt recommendations.
_MODEL_INPUTS = {
    "CheckpointLoaderSimple": {"ckpt_name": "checkpoint"},
    "CheckpointLoader": {"ckpt_name": "checkpoint"},
    "UNETLoader": {"unet_name": "diffusion"},
    "DiffusionModelLoader": {"unet_name": "diffusion"},
    "CLIPLoader": {"clip_name": "text_encoder"},
    "DualCLIPLoader": {"clip_name1": "text_encoder", "clip_name2": "text_encoder"},
    "TripleCLIPLoader": {
        "clip_name1": "text_encoder", "clip_name2": "text_encoder", "clip_name3": "text_encoder",
    },
    "VAELoader": {"vae_name": "vae"},
    "UpscaleModelLoader": {"model_name": "upscale"},
    "ControlNetLoader": {"control_net_name": "controlnet"},
    "DiffControlNetLoader": {"control_net_name": "controlnet"},
    "LoraLoader": {"lora_name": "lora"},
    "LoraLoaderModelOnly": {"lora_name": "lora"},
}


def inspect_workflow_models(graph: dict) -> dict:
    """Return static evidence only; linked model names and custom loaders stay unresolved."""
    if not isinstance(graph, dict) or not graph or not all(
        isinstance(node, dict) and isinstance(node.get("class_type"), str)
        and isinstance(node.get("inputs"), dict)
        for node in graph.values()
    ):
        raise ValueError("需要 ComfyUI API 格式的 workflow（节点必须有 class_type 和 inputs）")

    models = []
    unresolved = []
    unrecognized_loaders = []
    inactive_lora_count = 0
    for node_id, node in graph.items():
        class_type = node["class_type"]
        inputs = node["inputs"]
        source = {"node_id": str(node_id), "class_type": class_type}
        for field, role in _MODEL_INPUTS.get(class_type, {}).items():
            value = inputs.get(field)
            entry = {**source, "input": field, "role": role}
            if isinstance(value, str) and value.strip():
                entry["filename"] = value
                if role == "text_encoder" and isinstance(inputs.get("type"), str):
                    entry["encoder_type"] = inputs["type"]
                models.append(entry)
            else:
                entry["reason"] = "模型输入不是静态文件名，无法确定"
                if isinstance(value, list) and len(value) == 2:
                    entry["link"] = value
                unresolved.append(entry)

        # The plugin's LoRA stack format also contains inactive catalog entries.
        stack = inputs.get("loras")
        items = stack.get("__value__") if isinstance(stack, dict) else None
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                if not item.get("active", False):
                    inactive_lora_count += 1
                    continue
                value = item.get("name")
                if isinstance(value, str) and value.strip():
                    models.append({**source, "input": "loras", "role": "lora", "filename": value})
                else:
                    unresolved.append({**source, "input": "loras", "reason": "启用的 LoRA 缺少文件名"})
        elif class_type not in _MODEL_INPUTS and "load" in class_type.casefold():
            unrecognized_loaders.append(source)

    return {
        "models": models,
        "unresolved_inputs": unresolved,
        "unrecognized_loaders": unrecognized_loaders,
        "inactive_lora_count": inactive_lora_count,
        "node_types": sorted({node["class_type"] for node in graph.values()}),
    }
