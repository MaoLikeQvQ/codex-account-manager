# MaoX 账号管理器

本地 macOS 桌面工具，用于切换 Codex 官方 ChatGPT 账号与其他 Responses 兼容渠道，并把现有 Codex 对话统一归属到当前 Provider。

## 安装与升级

目前提供 Apple Silicon（arm64）版本。前往 [GitHub Releases](https://github.com/MaoLikeQvQ/codex-account-manager/releases/latest) 下载 DMG，将「MaoX 账号管理器.app」拖入「应用程序」，再从应用程序或启动台打开。

账号和设置保存在用户目录，与应用包分离。替换应用或清理项目的测试构建不会删除账号；正常启动读取原有账号，无需重新添加。`CODEX_HOME` 和 `MAOLIKE_CODEX_HOME` 可用于指定隔离目录，测试时使用空目录会显示空账号列表。

本地源码打包与安装方法见下方「打包」。当前构建使用本地临时签名，尚未配置 Apple Developer ID 签名或公证。

## 界面与操作

应用默认进入总览，左侧提供总览、账号管理、用量明细、实时请求和工具设置。界面采用浅灰背景、白色紧凑卡片与蓝色强调色，也支持深色主题；主题选择保存在本机。

| 页面 | 主要操作与展示 |
| --- | --- |
| 总览 | 当前账号、官方剩余配额、所选范围的 Token、API 等价估算费用、请求数、最近响应的时段分布及活跃模型。兼容渠道显示连接信息，未知数据显示「—」 |
| 账号管理 | 桌面窗口每行两个账号，窄屏单列。兼容账号显示名称、服务地址和操作；官方卡片与其同高，右侧用透明区域竖排显示 `5h`、`7d` 配额短条与百分比，重置时间和金额预估可悬浮查看 |
| 用量明细 | 按模型查看输入、缓存、输出、思考 Token、用量占比和费用估算，支持时间范围、模型筛选、同步参考价与 CSV 导出；少量记录时面板随内容收拢 |
| 实时请求 | 查看今天的本机逐响应记录、TPS、首响、总耗时、Token 与网络事件，自动刷新并支持手动刷新和分页 |
| 工具设置 | 鹈鹕 SVG 测试、Custom ImageGen 配置与应用、检查和安装更新 |

添加兼容渠道时只需填写 Base URL 和 API Key，模型目录 URL 可选；填写目录地址后自动启用渠道目录，留空使用内置目录。账号名称可选，默认使用服务域名。已有配置可展开粘贴导入；编辑账号保留已有连接参数，保存不会自动切换账号。

账号列表隐藏模型名称、「未启用」和「额度受限」文字；蓝色边框和「使用中」按钮标识当前账号。待应用修改和读取失败仍会提示，完整连接与额度信息可进入「详情」查看。「使用」才会切换账号，保存账号仅更新档案。

窗口默认以最小尺寸 960 × 640 打开，可手动放大。最小窗口按标题栏下约 960 × 612 内容区检查：操作、表头和分页保持可见，长列表在记录区内滚动。侧边栏底部提供启动或重启 Codex 的入口。

总览时段分布只统计当前已加载的最近响应，不代表完整历史分布。用量按 Provider 汇总，多个同 Provider 账号合并统计；估算金额不是服务商账单或订阅扣费。

## 网络请求事件

“实时请求”页新增“网络事件”视图，记录所有 Provider 已接入的 Codex HTTP/SSE 与 WebSocket 模型请求事件，失败和重试即使没有生成会话用量记录也可显示。固定显示今天的最新记录，支持刷新和分页；显示模型、会话、传输类型、目标地址（仅在事件提供时）、HTTP 状态、事件耗时及固定错误分类。当前本机 CLI 探测仅提供 /responses 路径，未提供目标主机，页面对此明确标注。HTTP 200 只表示响应头已返回，流完成或流失败单独显示，不计入响应次数和费用统计。

采集沿用 Codex 的本地 OTLP 导出，不修改模型请求的路由，不安装 HTTPS 解密证书。需完整退出并重新打开 Codex，使导出配置生效；管理器关闭期间、进程未配置导出或导出前退出的事件可能缺失，不能声称覆盖全部网络流量。已存在的外部导出配置保持原样，不会自动覆盖。定时唤醒直接使用 HTTP 请求，其结果显示在唤醒对话框，不经过 Codex OTLP 收集器。

只保存允许的元数据；不保存提示词、回复、工具参数、授权头、令牌、原始错误文本。地址去掉用户名、密码、查询参数和片段，仅保留来源及已知模型路由，自定义路径隐藏。错误只保留超时、DNS、TLS、连接、授权、限流等固定分类；未上报的信息明确显示缺失，无法追补。旧版计时库的历史事件不会伪造成新网络记录。

## 官方账号定时唤醒

在“账号管理 → 定时唤醒”中设置请求模型和每天的一个或多个时间点（最多 48 个）。启用后，每个时间点自动读取当时保存的全部官方账号，逐个发送固定消息 hi；新增官方账号自动参与，兼容渠道不参与。配置默认关闭，保存后生效，不切换当前账号或改写会话归属。

按本机时区执行；电脑恢复或管理器启动后，补执行当天最早错过的时间点，并把当天后续时间点按延迟顺延；再次错过时继续累计延迟。顺延至次日的旧时间点跳过，次日恢复原定时间。新启用或修改时间点时，从保存时刻开始生效；只修改模型或保存相同时间点不重置当天的顺延。同一天同一原定时间点不会因普通重启重复发送；上一轮尚未完成时等待结束，再将等待时间计入顺延。每个账号最多等待 90 秒，单个失败继续处理其他账号。对话框显示下次执行时间、当天累计顺延及最近一轮各账号结果，也可以保存设置后点击“立即唤醒全部”，确认后发送一次。

每次发送产生真实模型请求并消耗账号额度，请选择所有官方账号均可使用的模型；请求完成不代表一定触发额度周期。任务直接使用各官方账号的授权向官方 Codex Responses 接口发送 HTTP 流式请求，不启动 CLI，不保存唤醒会话。收到完整响应结束事件后才记为成功；失败不自动重试。授权过期时显示重新登录提示。设置及最近执行状态保存在管理器目录的 official-wakeup.json，其中不保存令牌、模型回复或对话内容。

## 账号导入与切换

添加兼容账号时可以直接粘贴渠道提供的 `config.toml` 和 `auth.json`（或 API Key）。来源 Provider ID 用于找到对应配置并建议账号名称。切换兼容账号时沿用 Codex 当前选中的自定义 Provider，只更新 Base URL、API Key 和可选模型目录 URL；保留 Provider 名称、模型、推理强度及其他已有连接设置。当前为官方 `openai` 或未选择 Provider 时，初始化独立的 `MaoLocal` 兼容入口，避免覆盖官方登录配置。

导入保留模型、推理强度、模型目录地址、鉴权、原生模型发现开关，以及支持的请求头、环境变量和重试/超时连接参数。`web_search`、`suppress_unstable_features_warning` 等全局设置不随账号导入，页面列出未导入字段。普通编辑保留隐藏连接参数；重新导入会替换该账号的连接参数。账号档案中的模型仅用于验证连接，可留空；“读取模型列表”仅检测渠道目录接口，不能证明实际推理可用。

保存只更新账号档案。编辑当前账号后显示“待应用修改”，点击“应用修改”写入配置；点击另一个账号的“使用”直接写入其连接和 Key。切换保留 Codex 当前模型和推理强度，不使用账号档案中的模型；若配置中没有指定模型，则由 Codex 自行选择。模型列表由 Codex 自己维护，管理器不复制目录或改写模型缓存；写入前备份 config/auth，失败时回滚 config、auth 和账号库。账号切换后自动归纳历史，Codex 运行时配置需要重启后生效。

双击应用默认优先使用本机 8787 端口；被其他程序占用时依次尝试相邻端口，全部占用才由系统分配。窗口与请求计时始终使用实际监听地址。命令行显式指定的 `--port` 不自动更换，`--port 0` 使用系统分配端口。

窗口打开和普通状态响应不扫描历史会话；账号切换及启动前的待处理归纳会执行完整扫描。后台状态每 10 秒更新，首页当天用量每分钟自动更新，也可手动刷新；弹窗打开时暂停轮询，慢请求不会重叠。弹窗使用静态遮罩；点击遮罩不会关闭弹窗，关闭、取消和 Escape 仍可退出，避免误点丢失尚未保存的输入。macOS 原生窗口接收失焦后的首次鼠标点击，点击按钮时同时激活窗口并执行操作。

实时请求采用增量读取缓存，只保存白名单统计元数据；其他 Provider 仅检查会话头部。列表固定显示今天的最新 100 次响应，支持自动刷新、手动刷新和分页。有逐响应 `token_usage_record` 时优先使用并按响应 ID 去重，旧格式使用去重后的 `token_count` 用量事件；不会把两者重复计数。列表不返回对话正文、工具参数、私密文件路径或凭据。

## 完整流程

新增账号时先选择登录方式：

- OpenAI 官方账号：使用 Codex 自带的 ChatGPT 设备码 OAuth；管理器会打开官方验证页并显示一次性验证码，避免本机浏览器回调端口问题。每个账号的登录凭据作为独立本地档案保存，切换时写入当前 Codex 登录态，由 Codex 按官方登录态获取模型目录。若 Codex 已在运行，切换后点击“重启 Codex”使新凭据在新进程中生效。
- Sub2API 聚合渠道：使用 Sub2API 的 Responses Base URL + API Key，读取模型列表时按 Base URL 原地址、`<base_url>/models`、`<base_url>/v1/models` 的顺序读取候选模型。新增时选择「兼容渠道」，使用兼容模式与 HTTP/SSE；编辑已有 Sub2API 账号保留它保存的 API Key Mode 和 WebSocket 参数。
- 其他兼容渠道：使用 OpenAI Responses 兼容的 Base URL + API Key，读取模型列表时采用相同的多地址发现流程；验证连接模型可留空，验证连接时再填写。

## Sub2API 兼容边界

Sub2API 在本管理器中是连接类型，不是第二套账号系统。管理器不管理 Sub2API 内部的上游账号、额度、并发、粘性调度或计费，只管理 Codex 到 Sub2API 的本地连接投影。

| 能力 | 行为 |
| --- | --- |
| 模型发现 | 依次请求 Base URL、`/models`、`/v1/models`，兼容 `data[*].id` 与 `models[*].slug`；配置了 `model_catalog_url` 时使用该地址；失败时如实报错，允许手动填写模型 |
| 兼容模式 | `requires_openai_auth = true`，Key 仍写入当前 `auth.json` |
| API Key Mode | `requires_openai_auth = false`，添加 Sub2API 要求的 actor authorization 请求头；Key 仍只写入当前 `auth.json`，不进入 `config.toml` |
| HTTP/SSE | 使用默认 Responses HTTP/SSE 传输，不写 Provider 级 WebSocket 字段 |
| WebSocket | 沿用当前自定义 Provider 的 `[features].responses_websockets_v2`；首次初始化兼容入口时使用账号的传输设置，切回官方恢复接管前的值 |
| 会话归属 | 兼容账号沿用当前自定义 Provider，官方账号使用 `openai`；切换后在会话文件可安全修改时自动更新 JSONL 与 SQLite |

模型目录按账号配置应用。兼容账号开启“启用渠道模型目录”后，将保存的 `model_catalog_url` 与 `api_key_model_discovery = true` 写入 Codex；关闭时不应用目录地址并写入 `false`，使用内置目录，账号档案仍保留目录地址。这样避免“目录地址存在但发现关闭”导致 Codex 返回空模型列表。切换回官方账号时恢复首次接管前的发现开关，由 Codex 按官方登录态获取目录，不再强制关闭发现。切换账号保留 Codex 当前选用的 `model`，不使用账号资料中的验证模型覆盖它。保存账号后需点击“应用修改”或“使用”，Codex 已运行时需重启生效。

CPA 支持目录接口的版本可填写 `http://localhost:8317/v1/models`，Codex 会自动附加 `client_version` 并读取完整目录及推理选项；地址应由渠道提供，目录请求会携带该渠道的认证信息。普通 OpenAI `data[*].id` 列表不等于 Codex 完整目录；“读取模型列表”只检查返回的模型 ID，不证明 Codex 元数据兼容或实际推理可用。CPA 目录由 CPA 维护，不等同于直连官方账号的实时目录。

管理器不修改 Codex App，不复制内置目录或读写 `models.json`、`models_cache.json`。仅在配置仍指向旧版管理器生成的 `~/.codex/models.json` 或管理器目录内 `bundled-model-catalog.json` 时，备份配置并清除此引用；保留远程目录地址、发现开关和旧目录文件。用户自定义的其他 `model_catalog_json` 保持原样；它优先于远程目录，使用渠道发现时需自行取消该本地覆盖。`responses_websockets_v2` 仍按兼容账号写入，切回官方账号恢复首次接管前的值，其他功能保持原样。

“验证连接”向填写的 Base URL 的 `/responses` 接口发送一次 `hi`，使用填写的验证模型和 Key；只有响应完成且返回非空文本才显示通过，并展示回复和耗时。该操作可能消耗少量额度，不保存、不切换账号，失败不自动重试。它与“读取模型列表”相互独立，保存账号不强制验证。验证使用 HTTP 请求，不验证 WebSocket 传输。

## 降智测试：鹈鹕骑自行车

在“工具设置 → 鹈鹕测试”中，使用 Codex 当前配置的模型和账号推理强度，发送固定的英文提示词，要求模型只返回一幅“鹈鹕骑自行车”的独立 SVG。官方账号走 Codex 官方 Responses 接口，兼容账号沿用保存的 Base URL、Key、请求头和查询参数，测试传输使用 HTTP/SSE。若当前配置未指定模型，需先设置模型才能运行测试。

打开测试窗口不会发送模型请求；点击“开始测试（1 次请求）”才会调用，可能消耗额度。失败、超时及重定向均不自动重试，运行中禁止重复提交。账号或默认模型已变化时拒绝旧页面的提交；待应用修改须先应用。测试不会切换账号、改写模型配置或写入历史会话。

结果展示 SVG 预览、原始回答、请求模型、接口自报模型、推理强度和总耗时。预览只保留静态 SVG 绘图内容，以图片方式加载，不执行模型脚本或加载外部图片；原始回答保持不变，可导出为文本。未返回合法 SVG 时保留回答并说明原因。可以观察鸟的形态、车架双轮和身体与车的空间关系，但单次图形不能证明模型身份、推理能力高低或是否发生降智。

## Custom ImageGen

工具页可安装独立的本地 MCP 图片工具。它与 `custom-imagegen-plugin` 使用同一调用契约：管理器使用 Images API，支持文本生成、参考图创作、单目标编辑、最多 16 张输入图和基于 `savedPath` 的连续修改；生成结果另存，不覆盖原图，也不会自动重试可能计费的失败请求。

独立图片允许并发调用，也可使用 `generate_images` 批量生成（每批 1–8 张，默认并发 3、最多 4）；依赖上一张结果的编辑须等待。插件通过 MCP 进度通知报告生成阶段、已用时和批量完成数量，等待时每 10 秒更新；供应商未提供真实渲染进度时不显示虚构百分比，实际呈现取决于 Codex 客户端。

图片配置只用于图片生成和编辑，不设置对话主模型；主模型由 Codex 当前选择决定。生成调用 `/images/generations`，带输入图片时调用 `/images/edits`。重新保存旧配置会移除 `mainModel` 并切换到 Images API。

图片工具支持“已管理账号”和“自定义链接”两种来源。已管理账号可固定选择账号列表中的任一兼容账号，使用其 Base URL/API Key；OpenAI 官方 ChatGPT/Codex OAuth 不能作为公开图片 API 的 Platform API Key，需另行配置 OpenAI Platform API Key。插件源码和发布产物来自 `custom-imagegen-plugin`，配置只保存账号库路径和账号名，不复制密钥。自定义链接的专用凭据保存在 `~/.maolike/codex/custom-imagegen.json`，权限为 `0600`。

统一显示名称为 `Custom ImageGen`，技能和 MCP 服务标识为 `custom-imagegen`。应用配置时自动迁移旧的 `maolocal-imagegen` MCP 配置和技能目录，保留原有图片配置与凭据。

“配置”只保存启用状态和请求参数；“应用”先比较应用内插件与 `~/.maolike/codex/imagegen_plugin/` 中的已安装版本，需要时安装或更新，再将 `~/.codex/config.toml` 的 MCP 启动路径更新到该稳定安装目录。MCP 配置只包含启动参数与图片配置文件路径，不包含凭据。应用完成后需重启 Codex，首次实际生成才会向渠道发请求并可能消耗额度。

图片配置中的“已管理账号”仅列出兼容渠道。官方 ChatGPT/Codex OAuth 凭据不能用于当前管理器配置的公开图片 API；使用 OpenAI Platform Images API 时，请选择“自定义链接”，填写 `https://api.openai.com/v1` 与 Platform API Key。

如果 Sub2API 前面还有 Nginx，需确认配置包含：

```nginx
underscores_in_headers on;
```

否则 `session_id` 等带下划线的粘性会话请求头可能被丢弃。

## 历史归属

切换账号后，管理器会将历史归属到当前账号。如果 Codex 桌面版或其他 `codex` 进程仍在运行，先保留待处理状态；关闭其他 Codex 客户端后，通过管理器启动或重启 Codex 时自动处理。历史待处理提示与账号配置的待重启状态分别显示；手动重启通过进程 PID 和启动时间识别。处理时管理器会：

1. 扫描 `~/.codex/sessions/` 和 `~/.codex/archived_sessions/` 的全部 rollout。
2. 创建只用于本次失败回滚的临时副本，不写入长期备份目录；操作结束即删除。
3. 只改写每一条 `session_meta.payload.model_provider`，其他 JSONL 行保持原字节。
4. 用事务同步 `threads` 和 `local_thread_catalog` 的 `model_provider`。

该操作幂等；已经属于当前 Provider 的历史不会重复改写。无法读取的会话会保留并提示未完成，失败后可重试。多个官方账号的原生 Provider 都是 `openai`，因此可以切换具体官方登录凭据，但历史归属无法按不同官方邮箱区分。旧对话中的 `encrypted_content` 可能与原 Provider 绑定，归属后仍能列出，但继续对话或压缩时可能需要切回原 Provider 或新建对话。

## 工程规划

前后端按功能划分目录、现有文件的迁移位置与拆分职责见 [目录与文件职责规划](docs/engineering-plan.md)。该文档对应已整理的本地目录及职责；测试仅保存在本地。

## 开发运行

```bash
cd codex-account-manager
pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python3 app.py
```

前端采用 React、TypeScript 与 MUI，Python 通过本地 HTTP 接口提供业务能力，pywebview 提供原生桌面窗口。前端构建需要 Node.js 22.12 或更高版本（建议 Node.js 22 LTS）。源码位于 `frontend/`，构建后的静态文件写入 `web/`。修改前端后重新执行 `npm --prefix frontend run build`；类型检查使用 `npm --prefix frontend run typecheck`。发布的 `.app` 只包含前端静态文件，无需用户为界面安装 Node.js；独立图片 MCP 工具仍使用它自己的 Node.js 运行时。

前端开发可在 Python 服务启动后另开终端执行 `npm --prefix frontend run dev`，通过 Vite 开发页面访问代理的 `/api`。自动化测试、测试辅助文件和 Playwright 配置仅保存在本机，不提交 Git，新克隆不包含这些文件。已有本地测试时，浏览器回归使用隔离目录和模拟 API，不读取真实账号或执行真实配置修改：先执行 `cd frontend && npx playwright install chromium webkit`，再在项目根目录执行 `npm --prefix frontend test`。已有本机 Chrome 时，可用 `PLAYWRIGHT_CHROMIUM_CHANNEL=chrome npm --prefix frontend test -- --project=chromium`。

本地已保留 Python 测试文件时运行：

```bash
python3 -m unittest discover -q
```

手写源文件按职责拆分，单文件不超过 1000 行。`frontend/` 包含 React 界面与 MUI 主题；`web/` 为构建输出，不手动修改。`maox/` 按账号、历史、用量、请求、图片、唤醒、桌面与更新等能力归类；本地测试集中在 `tests/` 并由 Git 忽略。`imagegen_plugin/server.cjs` 是打包的第三方生成产物，不作为手写模块维护。

用量统计只读 `~/.codex/sessions/` 和 `~/.codex/archived_sessions/` 中所选时间范围更新的 JSONL，不向页面返回对话内容。统计按 `session_meta.model_provider` 归属；多个官方账号同属 `openai` Provider，兼容账号按激活时实际使用的 Provider 分组统计，无法按邮箱或 Key 分别计量。估价优先同步公开参考源 [models.dev](https://models.dev/api.json)，失败时依次尝试 LiteLLM 与 OpenRouter；全部失败则使用上次缓存或内置的 [OpenAI API Standard 参考价](https://developers.openai.com/api/docs/pricing)。API 长上下文按单次输入超过 272K token 判断；本地事件未记录实际速度档位、渠道倍率或所有账单调整，因此金额仅供参考。

在「用量明细」点击「同步模型价格」可立即拉取公开参考价，更新用量明细和请求记录中的估算。同步失败会提示原因。兼容渠道也按公开参考价估算，实际扣费以渠道账单为准。

## 数据与安全边界

| 路径 | 用途 |
| --- | --- |
| `~/.maolike/codex/codex_accounts.json` | 账号库，权限 `0600` |
| `~/.maolike/codex/official-wakeup.json` | 定时唤醒设置及最近执行结果，不保存令牌或回复 |
| `~/.maolike/codex/request-timing.sqlite` | 脱敏请求计时与网络事件 |
| `~/.maolike/codex/api-prices-cache.json` | 公开参考价缓存 |
| `~/.maolike/codex/history_state.json` | 最近历史归属结果，不含对话正文 |
| `~/.maolike/codex/custom-imagegen.json` | 独立图片工具配置与凭据，权限 `0600` |
| `~/.maolike/codex/imagegen_plugin/` | 已应用的版本化图片 MCP 运行时 |
| `~/.maolike/codex/backups/` | 写入前备份，目录 `0700`、文件 `0600` |
| `~/.codex/config.toml` | 当前 Codex Provider 与默认模型 |
| `~/.codex/auth.json` | 当前账号的 API Key 或官方 OAuth 登录凭据 |

- 本地服务只监听 `127.0.0.1`。
- 状态 API 只返回凭据是否存在，不会向 WebView 回传 API Key、访问令牌或刷新令牌。
- Sub2API API Key Mode 不把 Key 写入 `config.toml` 或前端状态；当前活动 Key 与其他自定义渠道一样只写入权限为 `0600` 的 `auth.json`。
- 切换账号后自动归属历史；Codex 仍在运行时先保留待处理状态，在可安全修改会话文件时执行，失败会提示并重试。
- v5/v6/v7 账号库首次读取时自动迁移到 v8，并先创建备份；迁移不改变已有 `provider_id`、Key、默认模型或活动账号。
- 当前只支持 `wire_api = "responses"`；只支持 Chat Completions 的渠道需要先由上游网关转换为 Responses。

## 打包

```bash
./build.sh
```

脚本先按锁文件安装前端依赖并构建 React 页面，再使用 PyInstaller 打包 Python 与 `web/` 静态文件；`frontend/node_modules/` 不进入应用包。

产物：

- `dist/MaoX 账号管理器.app`
- `dist/MaoX-Account-Manager-<版本>-arm64.dmg`，打开后拖入 Applications 安装

本机安装时替换 `/Applications/MaoX 账号管理器.app`，保留 `~/.maolike/codex/` 和 `~/.codex/`。`build/` 是中间产物，`dist/` 是本地应用与安装镜像，均不提交 Git；验证安装后可以删除测试应用与中间目录，只留需要分发的 DMG。

## GitHub 发布与应用更新

推送到 `main` 后，GitHub Actions 在 Apple Silicon macOS runner 上执行前端类型检查、打包与校验，不运行仅保存在本机的自动化测试，生成独立版本的 GitHub Release，附带 DMG 和 `update.json`。本地提交需推送到 GitHub 才会触发；其他分支不发布。也可在 Actions 手动运行。

版本采用 `maox/version.py` 的主版本、次版本与工作流运行序号（例如 `2.11.123`）。重新运行同一次工作流复用版本。工作流成功上传后才公开 Release 并标记 Latest；失败保留上一个可用版本。

应用启动自动检查公开仓库 Latest 的更新清单；工具页可手动检查。点击“更新并重启”后校验文件大小、SHA-256、应用标识、版本与代码签名，在安装目录准备新版副本，自动退出、替换并重新打开应用。替换或启动命令失败时尝试恢复旧版。账号数据独立保存在用户目录，更新不会随安装包覆盖。需要先安装到可写目录；从 DMG 或源码运行不支持自动替换。安装错误记录在 `~/Library/Logs/MaoLocal-Codex-Manager/update.log`。旧版 2.11.4 需通过原有 DMG 方式安装一次支持自动替换的新版，此后直接在应用内更新。

发布目标在 `maox/version.py` 的 `UPDATE_REPOSITORY` 配置。自动更新目前要求公开下载渠道，不在应用内保存 GitHub Token。构建仅支持 Apple Silicon，使用本地临时签名，尚未配置 Apple Developer ID 签名或公证。

初次发布前在 GitHub 仓库 Actions 中允许工作流运行。工作流使用自带 `GITHUB_TOKEN` 和 `contents: write`，无需配置个人访问令牌。源码不包含账号库、认证文件、运行日志和本地产物；DMG 通过 Release 发布。
