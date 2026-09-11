# `comfyui_txt2img` 使用说明

这份说明同时面向项目维护者和会调用 AstrBot 工具的 LLM。工具的真实签名以 `main.py` 中的 `comfyui_txt2img` 为准；本文解释参数、提示词格式、编码规则和常见错误。

## 一句话

需要出图时调用 `comfyui_txt2img`。先确认目标 workflow 声明的模型和编码器，再按照用户的人格／系统提示词、模型资料和本次需求决定 prompt 的语言、结构与风格。把正向内容放进 `prompt`，负面内容放进 `negative_prompt`；只有用户明确指定且名称在可用列表中时才传 `workflow`。

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

当当前 workflow 开启 LoRA 控制并提供可用清单时，使用：

```json
{
  "prompt": "<lora picks=\"character.safetensors:0.8@1, style.safetensors:0.5\"> 1girl, standing, city street",
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
- `@1` 选择第 1 个触发词候选，`@1+2` 同时选择第 1、2 个候选；省略 `@...` 则使用默认提示词候选。
- `!clear_defaults` 是控制项，用于本次请求清除工作流中原本启用的默认 LoRA：`<lora picks="!clear_defaults, character.safetensors:0.8">`。
- 选中的 LoRA 可能自动注入其提示词提示；不要重复手写同一组触发词。
- 名称必须来自当前 workflow 的清单。找不到时插件会跳过该项，不要假设任意磁盘文件名都可用。

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
- **LLM 设置**：`llm_settings.system_prompt` 控制普通对话的绘图规则；默认内容只定义助手职责和协议，不规定模型提示词风格。`environment_prompt` 留空或填写当前实例的模型资料、已安装 MCP/skill 及使用条件，插件不会预置这些内容。插件会追加运行时 workflow 模型列表。`multi_image_mode` 控制多图分段，`discard_prompt_from_history` 控制是否从历史丢弃绘图提示词，`force_draw_when_no_prompt` 开启自动补图，`target_image_count` 设置自动补图目标数量。
- **LoRA 控制**：`llm_settings.lora_control.enabled` 开关；`inject_catalog_into_system_prompt` 注入当前 workflow 清单；`inject_selected_prompt_hints` 注入选中触发词；`keep_workflow_defaults_when_selected` 控制是否保留默认 LoRA；`max_lora_count` 控制最多选择数。
- **输出与权限**：`control` 中的冷却、白名单、管理员和敏感词策略决定谁可以调用工具；这些是部署策略，应在实例配置中设置。

### 工作流文件和运行时列表

将 ComfyUI 的 **Save (API Format)** JSON 放入插件持久化数据目录的 `workflow/` 子目录，并在插件配置中选择它。插件启动时扫描 JSON，运行时把可用文件名注入 LLM 上下文；切换 workflow 时会按文件名或 stem 重新加载对应 JSON。项目仓库中的 `workflow/` 仅用于默认模板，具体实例文件属于部署数据。

### 管理命令

管理员可以使用 `/comfy_ls` 查看运行时列表，使用 `/comfy_use <序号> [input_id] [output_id]` 热切换默认 workflow，使用 `/当前工作流` 查看当前设置。命令切换只改变当前插件实例状态，不会改变本文档或仓库模板。

## LLM 速查

1. 先判断用户是否真的要出图；需要时先确认 workflow 和模型信息。
2. 信息不足时调用 `comfyui_workflows`，再按用户人格／系统提示词、`environment_prompt` 和模型资料决定 prompt 形式；不要预设标签或语言。
3. `negative_prompt` 独立传入；用户明确给出 workflow 且名称在列表中时才传 `workflow`，否则省略。
4. 需要 LoRA 时只使用 `<lora picks="...">`，不要 HTML/URL 编码；选择依据来自当前清单和用户要求。
5. JSON 的引号交给序列化器转义；不要把 `/画图` 的命令行选项混入工具参数。
6. 根据工具真实返回说明成功、失败或部分成功。
