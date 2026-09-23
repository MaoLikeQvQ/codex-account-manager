# MaoLocal Codex 管理器

本地 macOS 桌面工具，用于切换 Codex 官方 ChatGPT 账号与其他 Responses 兼容渠道，同步对应模型目录，并把现有 Codex 对话统一归属到当前 Provider。

## 界面与操作

- **账号**：左侧列表查看账号，右侧显示连接与状态；“使用此账号”才执行切换。编辑、验证连接和新增官方授权分别提供明确入口。
- **模型**：默认模型与显示选择先暂存，点击“应用到 Codex”后执行。刷新只读取候选模型；支持搜索、放弃更改和恢复官方模型列表。跨页面保留草稿，切换账号前提醒放弃未应用的修改。
- **恢复官方模型列表**：固定恢复 GPT-5.6 Luna / Sol / Terra、GPT-6 Astra / Luna / Sol 共 6 个模型，替换目录并保存当前账号选择；默认模型仍在列表中则保留，否则改为 GPT-5.6 Luna。这是预设目录，不代表渠道调用验证通过。
- **工具**：独立执行历史会话归属；图片生成支持分为“配置”和“应用”，配置只保存选择，应用负责安装或更新插件并写入 MCP 配置。
- **首页用量**：桌面窗口采用 3:2 比例，首屏汇总当前 Provider 的消耗 token、输入、缓存输入、输出与估算费用；可选今天、昨天、近 7 天或指定日期。官方登录显示 credits，兼容渠道显示 API 美元价。未知模型不计价，费用不是渠道账单或实际订阅扣费。
- **启动 Codex**：全局入口，使用当前已保存的配置。未应用的模型草稿不会随启动自动保存。

模型应用沿用现有两步接口：渠道目录写入及筛选能力校验成功后保存默认模型。第二步失败时前一步可能已经生效，页面会保留失败原因和草稿，不宣称整个操作已回滚。官方账号只保存默认模型，不处理渠道目录。

## 完整流程

新增账号时先选择登录方式：

- OpenAI 官方账号：使用 Codex 自带的 ChatGPT 设备码 OAuth；管理器会打开官方验证页并显示一次性验证码，避免本机浏览器回调端口问题。每个账号的登录凭据作为独立本地档案保存，切换时写入当前 Codex 登录态，并使用 Codex 内置官方模型目录。若 Codex 已在运行，切换后点击“启动 Codex”使新凭据在新进程中生效。
- Sub2API 聚合渠道：使用 Sub2API 的 Responses Base URL + API Key，按 Base URL 原地址、`<base_url>/models`、`<base_url>/v1/models` 的顺序尝试载入模型。普通新增只需要填写连接信息；API Key Mode 和 WebSocket 保留在高级连接参数中，需要时再打开。
- 其他兼容渠道：使用 OpenAI Responses 兼容的 Base URL + API Key，采用相同的多地址模型发现流程并选择默认模型后保存。

模型面板的刷新按钮会把 Codex 官方目录与当前渠道候选模型按模型 ID 去重合并，不会立即覆盖本地目录。用户勾选需要保留的模型后，点击模型页的“应用到 Codex”，管理器会重新校验渠道目录，把合并后的完整目录写入 `~/.codex/models.json`，并将未勾选模型标记为隐藏，再校验当前安装的模型列表筛选能力并重启正在运行的 Codex。新版 Codex 原生支持已配置 catalog 时无需修改 App；旧版仍使用现有补丁。Sub2API 和其他兼容渠道共用这条本地 catalog 链路；桌面模型菜单随后使用本地 `model/list` 结果。旧版补丁限制了自定义 Provider 的远程 `available_models` 和桌面端 `additionalAvailableModels` 补充；新版使用 Codex 自身的目录筛选规则。`2.7.0` 仍兼容迁移旧版本在 Codex `26.810.52044` 上留下的模型筛选标记。

启动管理器和切换自定义账号都不会自动请求渠道模型接口。账号有已保存目录时直接复用该目录，并与官方目录合并去重；没有账号目录时复用当前本地 `models.json`，本地目录也为空时使用官方目录或账号已保存的默认模型。Codex App 更新后，管理器会重新读取新安装的内置目录；点击模型页“刷新”可预览新增官方模型，通过管理器启动 Codex 时会将它们补入本地目录并重新校验目录筛选能力，保留渠道模型的显示选择。启动补入过程不请求渠道接口；只有用户点击刷新、验证账号或显式注入模型目录时才会请求渠道模型列表。三种候选地址均不可用或均未返回模型时，使用 Codex 内置的官方模型目录，不会把第三方 API Key 发送给 OpenAI。

管理器不创建第二个 Codex App。当前安装若原生支持本地 catalog，管理器不会修改或重签名 App。旧版需要补丁时，修改前会把原始 `app.asar`、内置 `codex` 二进制、`Info.plist`、主程序签名、`CodeResources` 和完整 `Sparkle.framework` 备份到 `~/.maolike/codex/backups/codex-app-patches/`；若代码签名失败会自动恢复。注入前会先完整退出 Codex，避免修改运行中代码导致签名页失效；旧版注入时会按 Sparkle 要求逐个统一签名更新组件。官方 App 更新会覆盖旧补丁；更新后通过管理器启动自定义账号时会重新检测，新版原生能力会直接使用，未知筛选结构则拒绝修改。

同步失败会保留上一份可用目录，不会写入空文件或半成品。

## Sub2API 兼容边界

Sub2API 在本管理器中是连接类型，不是第二套账号系统。管理器不管理 Sub2API 内部的上游账号、额度、并发、粘性调度或计费，只管理 Codex 到 Sub2API 的本地连接投影。

| 能力 | 行为 |
| --- | --- |
| 模型发现 | 依次请求 Base URL、`/models`、`/v1/models`，兼容 `data[*].id` 与 `models[*].slug`；均失败时使用 Codex 内置官方目录 |
| 模型注入 | 继续生成本地 `models.json`、写入 `model_catalog_json`；新版使用原生筛选，旧版才修改 App |
| 兼容模式 | `requires_openai_auth = true`，Key 仍写入当前 `auth.json` |
| API Key Mode | `requires_openai_auth = false`，添加 Sub2API 要求的 actor authorization 请求头；Key 仍只写入当前 `auth.json`，不进入 `config.toml` |
| HTTP/SSE | 使用默认 Responses HTTP/SSE 传输，不写 Provider 级 WebSocket 字段 |
| WebSocket | 只确保 `[features].responses_websockets_v2 = true`；不会删除或覆盖 `[features]`、MCP、插件等其他配置 |
| 会话归属 | 继续使用账号保存时的稳定 `provider_id` 更新活动/归档 JSONL 与 SQLite，不使用显示名称，也不因迁移改变 ID |

管理器不再生成 `supports_websockets`；读取旧账号库时也会清除此遗留字段。切回 HTTP/SSE 时不会把全局 `responses_websockets_v2` 强制改为 `false`，避免影响官方账号或用户的其他 Provider 配置。

## 图片生成支持

工具页可安装独立的本地 MCP 图片工具。它与 `custom-imagegen-plugin` 使用同一调用契约：管理器使用 Images API，支持文本生成、参考图创作、单目标编辑、最多 16 张输入图和基于 `savedPath` 的连续修改；生成结果另存，不覆盖原图，也不会自动重试可能计费的失败请求。

图片配置只用于图片生成和编辑，不设置对话主模型；主模型由 Codex 当前选择决定。生成调用 `/images/generations`，带输入图片时调用 `/images/edits`。重新保存旧配置会移除 `mainModel` 并切换到 Images API。

图片工具支持“已管理账号”和“自定义链接”两种来源。已管理账号可固定选择账号列表中的任一兼容账号，使用其 Base URL/API Key；OpenAI 官方 ChatGPT/Codex OAuth 不能作为公开图片 API 的 Platform API Key，需另行配置 OpenAI Platform API Key。插件源码和发布产物来自 `custom-imagegen-plugin`，配置只保存账号库路径和账号名，不复制密钥。自定义链接的专用凭据保存在 `~/.maolike/codex/custom-imagegen.json`，权限为 `0600`。

“配置”只保存启用状态和请求参数；“应用”先比较应用内插件与 `~/.maolike/codex/imagegen_plugin/` 中的已安装版本，需要时安装或更新，再将 `~/.codex/config.toml` 的 MCP 启动路径更新到该稳定安装目录。MCP 配置只包含启动参数与图片配置文件路径，不包含凭据。应用完成后需重启 Codex，首次实际生成才会向渠道发请求并可能消耗额度。

官方账号不会把 ChatGPT OAuth token 当成 Platform API Key，也不会请求 `/v1/images`；它使用 Codex 官方账号链路和 `ChatGPT-Account-ID` 请求头。该能力依赖当前 Codex 后端协议、账号权益、地区、额度和图片工具开放状态；OAuth 过期或 401 时不会自动重试可能计费的生成请求，需在管理器中重新激活或登录该账号。若要使用公开 OpenAI Platform Images API，请选择“自定义链接”，填写 `https://api.openai.com/v1` 与 Platform API Key。

如果 Sub2API 前面还有 Nginx，需确认配置包含：

```nginx
underscores_in_headers on;
```

否则 `session_id` 等带下划线的粘性会话请求头可能被丢弃。

## 历史归属

在工具页点击“归纳会话”并确认目标账号后，管理器会：

1. 扫描 `~/.codex/sessions/` 和 `~/.codex/archived_sessions/` 的全部 rollout。
2. 创建只用于本次失败回滚的临时副本，不写入长期备份目录；操作结束即删除。
3. 只改写每一条 `session_meta.payload.model_provider`，其他 JSONL 行保持原字节。
4. 用事务同步 `threads` 和 `local_thread_catalog` 的 `model_provider`。

该操作幂等；已经属于当前 Provider 的历史不会重复改写。多个官方账号的原生 Provider 都是 `openai`，因此可以切换具体官方登录凭据，但历史归属无法按不同官方邮箱区分。旧对话中的 `encrypted_content` 可能与原 Provider 绑定，归属后仍能列出，但继续对话或压缩时可能需要切回原 Provider 或新建对话。

## 开发运行

```bash
cd codex-account-manager
pip install -r requirements.txt
python3 app.py
```

测试：

```bash
python3 -m unittest -v
```

手写源文件按职责拆分，单文件不超过 1000 行。`manager_parts/` 包含账号、官方登录、模型、图片、历史、存储及用量模块；`test_*.py` 按相同边界组织。`imagegen_plugin/server.cjs` 是打包的第三方生成产物，不作为手写模块维护。

用量统计只读 `~/.codex/sessions/` 和 `~/.codex/archived_sessions/` 中所选时间范围更新的 JSONL，不向页面返回对话内容。统计按 `session_meta.model_provider` 归属；多个官方账号同属 `openai` Provider，无法分别计量。估价使用 [Codex credits 价表](https://learn.chatgpt.com/docs/pricing#token-rates) 或 [OpenAI API 价表](https://developers.openai.com/api/docs/pricing) 的 Standard 档，API 长上下文按单次输入超过 272K token 判断；本地事件未记录实际速度档位、渠道倍率或所有账单调整，因此金额仅供参考。

## 数据与安全边界

| 路径 | 用途 |
| --- | --- |
| `~/.maolike/codex/codex_accounts.json` | 账号库，权限 `0600` |
| `~/.maolike/codex/sync_state.json` | 最近同步结果，不含 Key |
| `~/.maolike/codex/history_state.json` | 最近历史归属结果，不含对话正文 |
| `~/.maolike/codex/custom-imagegen.json` | 独立图片工具配置与凭据，权限 `0600` |
| `~/.maolike/codex/imagegen_plugin/` | 已应用的版本化图片 MCP 运行时 |
| `~/.maolike/codex/backups/` | 写入前备份，目录 `0700`、文件 `0600` |
| `~/.codex/config.toml` | 当前 Codex Provider、模型和 catalog 路径 |
| `~/.codex/auth.json` | 当前账号的 API Key 或官方 OAuth 登录凭据 |
| `~/.codex/models.json` | 由当前渠道模型列表生成的 Codex catalog |

- 本地服务只监听 `127.0.0.1`。
- 状态 API 只返回凭据是否存在，不会向 WebView 回传 API Key、访问令牌或刷新令牌。
- Sub2API API Key Mode 不把 Key 写入 `config.toml`、同步状态或前端状态；当前活动 Key 与其他自定义渠道一样只写入权限为 `0600` 的 `auth.json`。
- 普通账号切换不会改写会话；只有用户确认“全部归纳”后才更新会话 Provider 元数据。
- 旧版 Codex 去除远程模型白名单时需要修改并在本机重新签名原 App；新版原生支持本地 catalog 时无需修改，保留官方签名。旧版补丁的 Sparkle 更新组件会同步使用相同的本地签名，官方更新成功后会覆盖补丁并恢复原版。
- v5/v6/v7 账号库首次读取时自动迁移到 v8，并先创建备份；迁移不改变已有 `provider_id`、Key、模型选择或活动账号。
- 当前只支持 `wire_api = "responses"`；只支持 Chat Completions 的渠道需要先由上游网关转换为 Responses。

## 打包

```bash
./build.sh
```

产物：

- `dist/MaoLocal Codex 管理器.app`
- `dist/MaoLocal-Codex-Manager-<版本>-arm64.dmg`，打开后拖入 Applications 安装

以后应从这个管理器进入 Codex，使用“启动 Codex”。直接点击原 Codex 图标不会执行新增内置模型合并、渠道模型同步或补丁校验。


## GitHub 发布与应用更新

推送到 `main` 后，GitHub Actions 在 Apple Silicon macOS runner 上执行测试、打包与校验，生成独立版本的 GitHub Release，附带 DMG 和 `update.json`。本地提交需推送到 GitHub 才会触发；其他分支不发布。也可在 Actions 手动运行。

版本采用 `app_version.py` 的主版本、次版本与工作流运行序号（例如 `2.11.123`）。重新运行同一次工作流复用版本。工作流成功上传后才公开 Release 并标记 Latest；失败保留上一个可用版本。

应用启动自动检查公开仓库 Latest 的更新清单；工具页可手动检查。点击“更新并重启”后校验文件大小、SHA-256、应用标识、版本与代码签名，在安装目录准备新版副本，自动退出、替换并重新打开应用。替换或启动命令失败时尝试恢复旧版。账号数据独立保存在用户目录，更新不会随安装包覆盖。需要先安装到可写目录；从 DMG 或源码运行不支持自动替换。安装错误记录在 `~/Library/Logs/MaoLocal-Codex-Manager/update.log`。旧版 2.11.4 需通过原有 DMG 方式安装一次支持自动替换的新版，此后直接在应用内更新。

发布目标在 `app_version.py` 的 `UPDATE_REPOSITORY` 配置。自动更新目前要求公开下载渠道，不在应用内保存 GitHub Token。构建仅支持 Apple Silicon，使用本地临时签名，尚未配置 Apple Developer ID 签名或公证。

初次发布前在 GitHub 仓库 Actions 中允许工作流运行。工作流使用自带 `GITHUB_TOKEN` 和 `contents: write`，无需配置个人访问令牌。源码不包含账号库、认证文件、运行日志和本地产物；DMG 通过 Release 发布。
