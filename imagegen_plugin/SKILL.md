---
name: custom-imagegen
description: 通过自定义供应商生成图片、使用参考图、编辑现有图片和连续多轮修改。适用于用户指定 Custom ImageGen，或需要使用已配置供应商处理照片、插画、海报和图片素材。
---

# Custom ImageGen

沿用 ImageGen 的需求整理、参考图角色、编辑保留项、检查与迭代方式，由本插件 MCP 发送图片请求。Codex 理解当前对话，插件接收明确的提示词和图片路径；插件不会自动读取聊天记录或知道附件内容。

## 配置

独立插件默认配置为 `~/.maolike/custom-imagegen-plugin/config.json`，Windows 在用户目录同一路径。通过 MaoX 管理器安装时使用 `~/.maolike/codex/custom-imagegen.json`，由 `CUSTOM_IMAGEGEN_CONFIG` 指定。自定义链接只需：

```json
{
  "baseUrl": "https://your-provider.example/v1",
  "apiKey": "在本地填写供应商 Key"
}
```

每次调用重新读取配置。也可配置 `credentialSource: "managed_account"`、`accountStorePath` 和 `accountName` 选择 `.maolike` 账号。官方账号会通过隔离 `CODEX_HOME` 委托本机 `codex app-server` 使用 ChatGPT OAuth 完成原生 `image_generation`；不会把 OAuth 当作 Platform API Key，也不会直接请求内部 `backend-api` 地址。自定义账号仍读取 Base URL/API Key。`CUSTOM_IMAGEGEN_CONFIG` 可以指定其他文件；`IMAGE_*` 环境变量优先。默认 Images API、gpt-image-2、600 秒超时，兼容已有 mode、imageModel、mainModel、outputDir、timeoutSeconds 配置。不要读取或展示密钥，也不要要求用户将 Key 发到聊天。

在工具目录找到本插件的 `imagegen_status` 和 `generate_image`。首次使用检查配置；状态检查不代表供应商连通。工具缺失时说明需要安装更新并新建任务；不要自行切换其他供应商、内置工具或 CLI。

## 理解对话与选图

- 无输入图：生成新图。用户提供图片仅参考风格、色调、人物或构图时，属于参考图创作。
- 用户要求保留现有图并修改其中内容时，属于编辑。将选中的图片作为 `edit_target`，其余参考图作为 `reference`，每张图用 description 明确用途。
- “继续改”“再把背景改成海边”：使用当前对话、当前分支最近一次成功结果的 savedPath。“第一张”“上一版”“原图”：选择用户明确指向的版本，不能固定使用最新文件。
- 若当前对话中有多个同样合理的目标且无法消除歧义，简短询问选哪张。失败结果不是新版本，后续仍从最近成功且符合用户意图的版本继续。
- 输入路径只来自用户提供的文件、可访问的附件路径或本任务的工具结果。编辑前使用 view_image 查看本地目标和参考图。不能编造路径、把附件 ID 当路径，也不能从输出目录挑其他任务的最新图片。
- 若附件只有视觉内容而宿主没有暴露可读取文件，说明需要可访问的本地图片文件；不能仅凭文字重画后宣称完成编辑。不要扫描聊天历史或认证文件来找附件。

## 调用

单张使用 `generate_image`；多张相互独立的图片允许并发调用，或使用 `generate_images` 批量生成（每批 1–8 张，默认并发 3、最多 4）。prompt 必填；可省略 action，存在 edit_target 时自动编辑，否则生成。编辑恰好需要一张目标图；参考图可多张，输入总数最多 16。

```json
{
  "action": "edit",
  "prompt": "只把衣服换成白色。保留人物面部、身份、姿态、发型、背景、光线和构图。",
  "input_images": [
    { "path": "/absolute/path/previous-result.png", "role": "edit_target", "description": "上一轮用户选中的版本，保持人物与场景" },
    { "path": "/absolute/path/reference.png", "role": "reference", "description": "仅参考服装款式，不复制参考人物或背景" }
  ]
}
```

路径由工具读取并上传真实图片字节。Images 模式有图片时走 edits，无图时走 generations；Responses 模式发送文本和图片。不要因为接口叫 edits 就把参考图创作误认为必须保留参考图全部内容。

兼容 size、quality、output_format，但不需要每轮询问技术参数。除非需求明确或项目约束需要，保留服务默认值。模型不支持某参数或图片输入时应报告失败，不得静默丢图、降级模型或改成纯文本生成。

## 提示词与局部修改

具体提示词只整理，不增加人物、物件、品牌文案或故事。简略需求可以补充必要构图与用途。准确保留用户指定文字。

按需要组织：用途、主体、场景、风格、构图、光线、逐字文案、修改内容、必须保留的内容。多图按上传角色说明用途；工具将编辑目标放在 Image 1，参考图按输入顺序排列。

局部修改写清对象、位置、修改方式和保留项，例如“只移除左下角杯子，补齐桌面纹理；其余人物、物品、镜头和光线保持”。优先一次针对性修改，再检查。当前支持自然语言局部编辑，不提供蒙版字段，也不保证区域外像素完全不变。

## 输出与多轮迭代

- 检查返回的实际图片：主体、文字、构图、修改区域及保留项。只有成功返回才可宣称完成。
- 返回 savedPath、parentPath 和 inputImages；parentPath 指向本轮编辑目标。所有结果另存，原图不覆盖。后续引用正确版本的 savedPath；回到原图时直接重用原路径，无需重新生成原图。
- 展示图片并报告实际保存路径。预览图默认位于 `$CODEX_HOME/generated_images/custom-imagegen/`（未设置时为 `~/.codex/generated_images/custom-imagegen/`）；已有 outputDir 配置仍优先。
- 项目使用的最终素材应复制到工作区或用户指定位置，避免项目只依赖默认输出目录。不要覆盖已有资产，除非用户要求替换。
- 多张独立图片可并发调用 generate_image，或使用 generate_images；依赖上一轮结果的编辑必须等待该结果，不能提前编造 savedPath。批量整批 600 秒上限，检查每项状态，勿把部分成功说成全部成功。
- 调用时请求 MCP 进度通知（`_meta.progressToken`，由宿主提供）。插件报告准备、提交、等待、保存、结束等阶段，等待时每 10 秒更新已用时；批量还报告已处理/总数和每张状态。无供应商真实进度时，不把阶段或耗时说成渲染百分比。宿主未请求进度时仍正常生成；界面如何呈现由宿主决定。
- 超时、取消、网络错误可能发生在计费后，不自动重试或整批重跑。已成功文件保留；明确失败原因后按用户意图处理。

官方账号使用本机 Codex app-server 委托；自定义供应商必须支持实际使用的生成、图片输入和编辑协议。
