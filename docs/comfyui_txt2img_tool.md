# `comfyui_txt2img` 使用说明

这份说明同时面向项目维护者和会调用 AstrBot 工具的 LLM。`comfyui_usage` 会按需读取本文件，并附上当前实例的 LoRA 开关和数量限制。工具的真实签名以 `main.py` 中的 `comfyui_txt2img` 为准。

## 一句话

本轮已按用户要求选择 ComfyUI 后，调用 `comfyui_txt2img`；遵循已有的生图后端优先级和确认要求。先确认目标 workflow 声明的模型和编码器，再按照用户的人格／系统提示词、模型资料和本次需求决定 prompt 的语言、结构与风格。把正向内容放进 `prompt`，负面内容放进 `negative_prompt`；只有用户明确指定且名称在可用列表中时才传 `workflow`。

## 按需查询入口

- `comfyui_usage`：无参数，只读返回本说明及当前实例状态；不扫描 LoRA 库存、不生图、不下载、不修改配置。
- `comfyui_workflows`：只读查询工作流模型声明及 `environment_prompt` 实例补充说明；已知目标名称时传 `workflow`，省略则列全部工作流。
- LoRA 的搜索、详情、下载和启停由独立的 LoRA MCP 负责。若当前工具集中提供 `search_local_inventory`、`get_local_lora_details`，可使用它们查询已安装条目；这些不是本插件注册的工具。只能调用本轮实际可用的工具。

插件不再将全量 LoRA 清单或全部工作流模型 JSON 自动拼进 system prompt。`comfyui_workflows` 中的 LoRA 仅是工作流模板内已启用的声明，不是本地库存查询。

若实例另外开启自动补图，补图的独立请求仅携带默认工作流的模型资料和实例补充说明，不携带全部工作流或 LoRA 库存。

## 工具参数

| 参数 | 类型 | 默认值 | 使用细节 |
| --- | --- | --- | --- |
| `prompt` | `str` | 无 | 必填。格式由目标模型和用户系统提示词决定，插件不会替你选择标签体系或语言。可包含 `<lora picks="...">`；不要把 `--neg`、`-wf` 等命令行选项写进来。 |
| `text` | `str` | 空 | `prompt` 为空时的兼容备用字段。正常调用只传 `prompt`。 |
| `negative_prompt` | `str` | 空 | 独立的负面提示词。未传时保留工作流 JSON 自带的负面词，并继续追加插件配置中的默认负面词。 |
| `workflow` | `str` | 默认 workflow | 可传可用列表中的完整文件名或不带 `.json` 的文件名。用户没有明确指定时省略；不能编造名称。 |
| `img_width` | `int` | 由 workflow 决定 | 当前不会覆盖工作流尺寸，仅为兼容保留，通常不传。 |
| `img_height` | `int` | 由 workflow 决定 | 当前不会覆盖工作流尺寸，仅为兼容保留，通常不传。 |
| `count` | `int` | `1` | 取值 1–16。大于 1 时插件并行提交多个任务，再按平台规则回收结果。 |
| `direct_send` | `bool` | `false` | `true` 逐张直接发送；`false` 返回转发卡片。webchat 等不支持转发节点的平台应传 `true`。 |

### 标准调用

```json
{
  "prompt": "根据用户系统提示词和目标模型资料编写的正向画面描述",
  "negative_prompt": "根据目标模型资料编写的负向约束",
  "direct_send": true
}
```

### 选择 workflow

```json
{
  "prompt": "符合用户要求的主体、动作、环境和风格描述",
  "workflow": "example_workflow.json",
  "direct_send": true
}
```

`workflow` 支持完整文件名和去掉 `.json` 的 stem，匹配不区分大小写；路径、带其他扩展名的值和列表外名称会被拒绝。工具调用使用字段名 `workflow`，不要传 `/画图` 命令的 `-w` 或把 `--workflow` 拼进 prompt。

### 查询 workflow 模型

`comfyui_workflows` 是只读工具。省略 `workflow` 时返回所有可用 workflow，传入名称时只返回目标 workflow。结果中的 `models` 来自 API JSON 中的静态 loader 输入，通常包含 checkpoint、diffusion、text encoder、VAE、upscale、controlnet 和启用的 LoRA；`unresolved_inputs` 表示动态链接或无法从文件名确定的输入，`unrecognized_loaders` 表示插件无法识别的 loader。结果是事实线索，不保证服务端已安装、节点分支实际执行或提示词语法已确定。

模型文件名、编码器类型和 LoRA 元数据只能用于选择查询方向，不能直接推出“应该使用英文 tags”“应该使用自然语言”或某种风格。MCP、skill、标签体系和写法由用户人格／系统提示词、本次请求、实例补充配置及用户指定模型资料共同决定。

## 正向提示词写法

插件只负责把 prompt 注入 workflow 的输入节点，不规定标签体系、自然语言、语言种类、权重语法或风格。先查看 `comfyui_workflows` 返回的模型声明和实例补充说明，再遵循用户的人格／系统提示词；如果模型资料不足，不要从文件名臆测提示词规则，应查询用户指定的资料或询问用户。

提示词可以是模型要求的标签、自然语言、结构化片段或它们的组合。逗号、括号、权重符号和换行是否有意义，均以目标模型资料为准；插件不会将它们自动转换。

## 编码、转义和符号

工具接收的是已经解析后的字符串：

1. 不要 URL 编码（例如不要把逗号变成 `%2C`），不要 Base64 编码，也不要把普通 tags 转成 HTML 实体。
2. JSON 请求中的字符串引号、反斜杠和换行由 JSON 库自动转义。手写 JSON 时，LoRA 标签属性的引号写成 `\"`；工具收到的实际字符串必须是 `<lora picks="...">`。普通 prompt 中的符号不需要额外转码。
3. 不要把 `&quot;`、`&#34;` 或反斜杠实体写进 LoRA 标签；插件不会把这些实体还原，标签就无法被识别。
4. LoRA 标签必须使用双引号属性，建议写在 prompt 开头附近，并且内部不要再放未转义的双引号。标签会在提交前剥离，剩余内容才是正向 prompt。
5. 普通 prompt 中保留目标模型需要的符号；换行是否保留由模型资料决定。如果使用 JSON 字符串，交由序列化器处理 `\n`，不要手动重复转义。

## LoRA 控制

先通过当前可用的 LoRA MCP 确认本地已安装的模型、名称和适用条件，再在开启 LoRA 控制的 workflow 中使用。查询到远端模型不代表已经安装。以下名称只是语法示例，不能直接照抄提交：

```json
{
  "prompt": "<lora picks=\"character.safetensors:0.8, style.safetensors:0.5\"> 1girl, standing, city street",
  "negative_prompt": "lowres, bad hands",
  "direct_send": true
}
```

格式为：

```text
<lora picks="文件名:强度@触发词序号, 另一个文件名:强度@1+2">
```

- 默认最多选择 4 个 LoRA；可通过 `llm_settings.lora_control.max_lora_count` 调整上限。
- 强度会按数值解析；建议使用 `0.0`–`2.0` 的小数，具体以当前工作流和模型效果为准。
- `@1` 选择插件解析出的第 1 个触发词候选，`@1+2` 同时选择第 1、2 个候选。仅在已确认候选编号时使用；不要把 MCP 搜索排名当作候选编号。省略 `@...` 时使用配置的 `prompt_hints`，或唯一的触发词候选；多个候选不会自动全选。
- `!clear_defaults` 是控制项，用于本次请求清除工作流中原本启用的默认 LoRA：`<lora picks="!clear_defaults, character.safetensors:0.8">`。
- 是否自动注入选中的触发词、是否保留默认 LoRA，以 `comfyui_usage` 返回的当前实例状态为准；自动注入关闭时需要自行编写完整提示词。不要重复手写同一组已自动注入的触发词。
- 使用 MCP 确认的 ComfyUI 相对文件名或已知别名，不传下载 URL。当前执行端仍通过 workflow、本地文件和 sidecar 做兼容解析；找不到时会跳过该项，不能假设任意名称都有效。关闭全量注入不会关闭这条执行路径。

## `/画图` 命令与工具调用的区别

下面是聊天命令的语法，只适用于 `/画图`、`/画图no` 和 `/重绘`，不适用于 LLM 工具的 JSON 参数：

```text
/画图 <prompt> [--workflow <名称>|-wf <名称>] [--count <数量>|-c <数量>] [--neg <负面词>|--negative <负面词>|-n <负面词>]
```

当前没有 `-w`、`-workflow` 或 `--wf` 别名。未识别的短选项会被当作 prompt 普通文本；若出现在 `-n` 后面，可能被当作负面提示词的一部分。因此 LLM 工具始终使用 `workflow` 和 `negative_prompt` 字段。

## 失败处理和发送方式

- 工具返回图片或明确错误字符串。不要在工具返回前声称已经生成，也不要伪造图片 URL。
- `count > 1` 会产生多个独立任务，单次最多 16 张；批量任务可能因队列、超时或某张图失败而部分成功。
- `direct_send=true` 适合 webchat 等不支持转发卡片的平台；普通 QQ/群聊通常可使用默认的 `false`。
- `img_width`、`img_height` 当前由 workflow 决定，传入它们不会替换 JSON 中的尺寸。

## 可配置位置

下面列出插件提供的配置入口和它们影响的行为；这里不包含任何特定部署的实际地址、文件名或模型值。

### AstrBot 插件配置

在 AstrBot 的插件设置中配置：

- **ComfyUI 连接**：`server_address` 指向 ComfyUI 或兼容 gateway 的 HTTP 地址。
- **工作流设置**：`workflow_settings.json_file` 选择默认 JSON；`input_node_id` 指定正向提示词节点；`neg_node_id` 指定负向提示词节点（可空）；`output_node_id` 指定输出节点。
- **基础参数**：`sub_config.negative_prompt` 会作为额外负面词追加；`sub_config.steps`、`sub_config.width`、`sub_config.height` 是兼容字段，当前尺寸和步数仍由 workflow 节点及步数 sidecar 决定。
- **LLM 设置**：`llm_settings.system_prompt` 补充绘图规则，插件保留自定义内容；自动附录仅提供简短工具入口和默认工作流名称。`environment_prompt` 可填写模型资料、已安装 MCP/skill 及使用条件，通过 `comfyui_workflows` 按需返回。`multi_image_mode` 控制多图分段，`discard_prompt_from_history` 控制是否从历史丢弃绘图提示词，`force_draw_when_no_prompt` 开启自动补图，`target_image_count` 设置自动补图目标数量。
- **LoRA 控制**：`llm_settings.lora_control.enabled` 保留执行控制；`inject_catalog_into_system_prompt` 已停用，旧配置即使为 `true` 也不会重新开启全量注入。`inject_selected_prompt_hints` 控制最终绘图 prompt 中的选中触发词，与 system prompt 的清单注入不同；`keep_workflow_defaults_when_selected` 控制是否保留默认 LoRA；`max_lora_count` 控制最多选择数。迁移阶段保留 `scan_directories` 和现有执行解析，不要因关闭注入而清空它们。
- **输出与权限**：`control` 中的冷却、白名单、管理员和敏感词策略决定谁可以调用工具；这些是部署策略，应在实例配置中设置。

### 工作流文件和运行时列表

将 ComfyUI 的 **Save (API Format)** JSON 放入插件持久化数据目录的 `workflow/` 子目录，并在插件配置中选择它。可用文件名和模型资料通过 `comfyui_workflows` 按需查询；切换 workflow 时会按文件名或 stem 重新加载对应 JSON。项目仓库中的 `workflow/` 仅用于默认模板，具体实例文件属于部署数据。

### 管理命令

管理员可以使用 `/comfy_ls` 查看运行时列表，使用 `/comfy_use <序号> [input_id] [output_id]` 热切换默认 workflow，使用 `/当前工作流` 查看当前设置。命令切换只改变当前插件实例状态，不会改变本文档或仓库模板。

## LLM 速查

1. 先确认用户确实需要出图，且本轮已选择 ComfyUI；首次使用或参数不明确时调用 `comfyui_usage`。
2. 信息不足时调用 `comfyui_workflows`，再按用户人格／系统提示词、`environment_prompt` 和模型资料决定 prompt 形式；不要预设标签或语言。
3. `negative_prompt` 独立传入；用户明确给出 workflow 且名称在列表中时才传 `workflow`，否则省略。
4. 需要 LoRA 时先通过实际可用的 LoRA MCP 查询，再使用 `<lora picks="...">`；不要编造名称或候选编号，不要 HTML/URL 编码。
5. JSON 的引号交给序列化器转义；不要把 `/画图` 的命令行选项混入工具参数。
6. 根据工具真实返回说明成功、失败或部分成功。
