# Krea 2 workflow templates

| Template | Base resolution | Saved image size |
| --- | --- | --- |
| `moody_krea_v7_API.json` | 768×1152 | 3072×4608 |
| `moody_krea_v7_fast_API.json` | 768×1152 | 1536×2304 |

Both use Moody Krea v7 FP8, 12 steps, CFG 1, Euler / simple, and one image.
They share the same model dependencies. The default keeps the native 4x output;
fast uses the same 768×1152 generation base, runs Remacri 4x, then resizes to
1536×2304 (compact 2x final output) to control transfer size. Fast keeps the
same sampling resolution and LoRA support; it reduces final image size, not
Remacri's 4x intermediate computation. PNG file size depends on content and
is not guaranteed to stay below 4 MB.

Plugin node settings: positive `5`, negative `6`, output `15`. Node `23` is
`Lora Loader (LoraManager)`; its MODEL output feeds sampler `13` and its CLIP
output feeds both prompt encoders. Output node `15` saves node `17` in the
default template and node `18` (final bicubic resize) in fast. Keep these node
IDs unchanged.

The templates list eleven reviewed Krea 2 LoRAs, **all disabled by default**.
Without a LoRA selection, node `23` passes MODEL/CLIP through unchanged and does
not load the listed LoRA files. Named inactive entries are intentional: the
current plugin does not recognize an empty LoRA list as an injectable stack.
Enable plugin LoRA control to select LoRAs dynamically. Other installed Krea 2
LoRAs can be appended through the plugin's configured inventory discovery.
Do not select Illustrious, Pony, or other incompatible LoRAs for these workflows.

LoRA names must be complete relative catalog keys, including the extension:
`ecosystems/krea2/Pantyhose.safetensors`. A basename that works on a direct
worker may be rejected by gateway inventory validation.

## Required models under the existing model-root mount

```text
diffusion_models/Moody-Krea-Mix-v7_00002__clean_fp8.safetensors
text_encoders/qwen3vl_4b_fp8_scaled.safetensors
vae/qwen_image_vae.safetensors
upscale_models/4x_foolhardy_Remacri.pth
loras/ecosystems/krea2/<selected LoRA>.safetensors
```

## Install/update

The operator updates plugin code from GitHub through AstrBot WebUI. Updating
the plugin only copies missing templates into persistent data; it does not
overwrite an existing same-name workflow. The operator must manually replace
the persistent workflow files when upgrading an existing template. Back up the
existing JSON before replacement. Agents must not write the AstrBot data paths.

Persistent directory: `data/plugin_data/astrbot_plugin_comfyui_pro/workflow/`.
This is distinct from the installed plugin source at `data/plugins/`.
Review any same-name `.steps.json` sidecars, which can override the 12-step
defaults. Leave unrelated workflow files and plugin settings unchanged.

The API result-wait default is restored to 120 seconds. This is independent
of AstrBot's outer tool-call timeout and does not extend that outer timeout.
