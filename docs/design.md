# MaoX 账号管理器 — v2 设计

## 目标

提供三条可验证闭环：

- 官方账号切换：隔离 CODEX_HOME 发起 ChatGPT 设备码 OAuth → 保存独立凭据档案 → 验证并可回滚切换 auth/config → 使用 Codex 内置模型目录。
- 渠道账号切换：原子替换 config/auth → 失败时整组回滚 → 标记活动账号。
- 历史归属：扫描全部 rollout → 创建操作内临时回滚副本 → 只改 session_meta → 事务更新 SQLite → 删除临时副本 → 全量复核。

Sub2API 只扩展渠道账号连接参数，不分叉账号切换和历史归属实现。

主流程采用渐进披露：粘贴配置作为新增兼容账号的入口；手动填写只需账号名称、服务地址和 Key，验证模型可选。Provider ID 与 Provider name 统一为 MaoLocal，目录地址、模型发现、鉴权和推理强度放在高级设置；编辑已有 Sub2API 账号保留连接模式。

## 界面结构

界面采用固定侧边栏与独立页面。默认进入总览，侧边栏依次提供总览、账号管理、用量明细、实时请求和工具设置，底部显示 Codex 状态与启动/重启入口。默认窗口 1180 × 820，最小 960 × 640（标题栏下按 960 × 612 内容区验收）；窄屏切换为顶部横向导航。

总览顶部展示当前账号。官方账号显示真实剩余配额与重置时间，未知值显示“—”，失败显示原因并允许刷新；兼容渠道显示当前模型和连接方式。三张统计卡片展示所选范围的 Token、估算费用及请求数，下方为最近响应的 24 小时时段分布与模型用量。时段分布仅对已加载的最近响应按小时汇总，不冒充完整历史统计。用量明细与实时请求保留紧凑统计栏、筛选、导出和内部滚动表格。

整体参考 GravityBox 的桌面应用布局：灰色侧边栏、浅灰页面、白色圆角卡片、淡蓝选中状态与蓝色配额条。账号页采用每行两个账号的紧凑网格，窄屏为单列。兼容渠道只显示名称、地址和操作，不显示模型名称、未启用或额度受限文字；当前账号由蓝色边框和使用中按钮标识，待应用修改保持提示。官方账号与第三方账号同高，保留套餐，5h、7d 配额在右侧 94px 透明区域内竖排，取消背景色与边框，采用浅灰轨道和右对齐百分比，重置时间和金额预估放在悬浮提示及详情，读取失败保持可见。总览兼容账号区与统计卡片减少留白，图表采用较低高度；用量面板按内容高度收拢，用量、实时请求与网络事件表格列宽适配最小桌面窗口，记录区域内部滚动，操作、表头及分页保持可见。侧栏不显示右侧分隔线。工具设置按模型扩展、系统更新分组。保留 MaoX 品牌图标与现有功能边界。

## 主题与交互

应用标识沿用石墨底、浅白 Code 字标与薄荷绿终端光标。`assets/maox-icon.svg` 为 Dock、应用图标、网页小图标和页面左上角的共同来源。macOS 打包时从 SVG 生成多尺寸 ICNS。

采用浅灰白与石墨灰主题，蓝色用于选中状态、配额条、焦点及主要操作。卡片使用 16px 圆角与轻量阴影，减少大面积边框。主题选择保存在本机，不随后台状态刷新重置。

| Token | 浅色 | 暗色 |
| --- | --- | --- |
| 页面背景 | #f5f6f9 | #121419 |
| 面板与弹窗 | #ffffff | #1b1e26 |
| 主文字 | #303238 | #edf0f6 |
| 次文字 | #7a7d86 | #a3adbf |
| 分隔线 | #edeef2 | #30343f |
| 主要操作与焦点 | #0866ed | #70acff |

MUI v9 的 Typography 使用 textSecondary 等语义颜色属性，sx 样式使用 text.secondary 等调色板路径，确保说明文字实际呈现次级颜色。系统字体用于界面，等宽字体仅用于模型、代码及数值。统一按钮、输入框、表格和弹窗状态，成功、警告、失败使用语义色。样式由 frontend/src/theme.ts 统一维护。

原生 WKWebView 使用系统方法签名实现 acceptsFirstMouse，允许失焦后首次点击同时激活窗口并执行操作。ManagerDialog 统一忽略 backdropClick；只由明确关闭、取消、Escape 或成功提交退出。后台状态和请求轮询在弹窗打开时暂停，业务面板保持挂载，防止输入和焦点被刷新重置。

## 鹈鹕骑自行车测试

入口位于工具设置，单独弹窗显示当前账号、默认模型和推理强度。只有显式点击开始才发送一次 Responses 请求，JSON 与 SSE 响应均支持，不跟随重定向、不重试。全局测试锁拒绝并发测试，账号配置写入锁保证测试期间不切换账号；前端暂停后台轮询并防止重复提交。待应用档案及过期账号/模型请求在调用前被拒绝。

官方请求固定使用 Codex 服务及当前已应用授权，核对账号 ID；兼容请求继承已有头部与查询参数。测试不自动修改或刷新凭据。结果保留完整原始回答，预览通过 SVG 静态元素过滤后作为图片展示，下载原始回答使用纯文本。结果是视觉观察材料，不自动生成智商分数。切换账号或修改默认模型会清除上一次结果。

## 模块

```text
app.py             本地 HTTP API、窗口入口
codex_manager.py   对外管理器入口、状态、Codex App 启动
manager_parts/     账号、官方登录、模型、图片、历史、存储、用量模块
frontend/          React/TypeScript/MUI 源码与隔离浏览器回归
web/               Vite 生成的静态资源
native_window.py   macOS 原生首次点击处理
test_*.py          按模块划分的隔离文件系统与模拟渠道契约测试
```

## 连接模型

账号库 v8 将“账号身份”和“连接实现”分开：

```text
account_type:     official | custom
connection_type: official | openai_compatible | sub2api
auth_mode:        legacy | api_key
transport:        http_sse | websocket
```

- `account_type` 保留官方 OAuth 与外部 Provider 的原有分流。
- `connection_type` 只决定外部 Provider 的配置投影；旧自定义账号迁移为 `openai_compatible`。
- `auth_mode` 与 `transport` 只允许用于 Sub2API。
- `provider_id` 是模型 Provider 和会话归属的键；兼容账号激活后统一为 `MaoLocal`，provider name 也固定为 `MaoLocal`，账号名称独立。旧账号库迁移保留旧 ID，普通切换不修改历史。
- Sub2API API Key Mode 的 Key 继续写入 `auth.json`，不使用 `experimental_bearer_token`，避免密钥进入 `config.toml` 及其备份。
- 模型发现和 WebSocket 开关按兼容账号明确写入；首次接管记录原值，切回官方账号恢复。Provider 不再写入 `supports_websockets`。

## 写入不变量

1. 账号切换前备份 `config.toml` 和 `auth.json`，切换事务失败时恢复旧内容。
2. 渠道账号使用统一 `MaoLocal` Provider；账号切换保留当前模型，目录文件、配置、凭据及账号库共同回滚。启动时只清除指向旧版管理器生成的 `models.json` 引用，不修改 Codex App。
3. Web 状态不包含 API Key 或官方 OAuth 令牌。
4. 账号切换后自动将历史归属到当前 Provider；若 Codex 仍在运行则保留待处理状态，在管理器启动或重启 Codex 前处理。处理同时更新 JSONL 和 SQLite，失败及部分成功均可见并可重试。
5. Sub2API 的 API Key 只写入 `auth.json`，WebSocket 功能按账号配置写入，切回官方恢复原值。
6. 从 Codex 自带命令提取完整内置目录写入管理器目录，官方及渠道账号统一指向它；启动 Codex 时为当前管理账号应用或刷新目录。渠道模型列表读取仍单独检测渠道接口，不将结果注入统一目录。原生模型发现配置保留，但被本地目录覆盖。
7. 图片工具使用独立 MCP，不修改 Codex 的模型目录或主模型设置。

## API

- `GET /api/state`
- `GET /api/usage?period=today|yesterday|7d|date&date=YYYY-MM-DD`（只读汇总当前 Provider 的所选时间 token 与官方价估算）
- `POST /api/benchmark/pelican`（Codex 当前配置模型的单次 SVG 测试）
- `POST /api/accounts/save`
- `POST /api/accounts/parse-config`（只解析粘贴配置，不写入、不联网）
- `POST /api/accounts/verify`（只读检测目录接口，不验证推理、不落库、不切换）
- `POST /api/accounts/official-login/start`
- `GET /api/accounts/official-login/status?login_id=<login_id>`
- `POST /api/accounts/official-login/complete`
- `POST /api/accounts/official-login/cancel`
- `POST /api/accounts/delete`
- `POST /api/accounts/activate`
- `POST /api/codex/launch`
- `POST /api/image-generation/configure`
- `POST /api/image-generation/apply`
- `POST /api/history/claim-all`

所有修改请求串行执行，避免账号切换和其他配置写入互相覆盖。

图片 MCP 的凭据来源独立于当前活动账号。`managed_account` 只在图片配置中保存账号库路径与账号名；运行时每次读取指定账号。官方账号使用保存的 ChatGPT OAuth access token 和 account ID 请求 Codex Responses SSE，绝不将 OAuth token 投递到 Platform `/v1/images`；自定义账号和自定义链接继续使用 Images/Responses 兼容接口。任何图片请求都不自动重试。

## Sub2API 回归矩阵

| 场景 | 最低验证 |
| --- | --- |
| 兼容模式 | `requires_openai_auth = true`、HTTP/SSE 默认关闭 WebSocket、`auth.json` 写 Key |
| API Key Mode | `requires_openai_auth = false`、actor header 存在、Key 不进入 config/public state |
| WebSocket | 全局 v2 feature 为 true、HTTP/SSE 切换为 false、切回官方恢复原值，其他 `[features]`/MCP 配置保持 |
| 模型发现 | 检测接受 `data[*].id` 与 `models[*].slug`；目录失败必须报错；原生发现需完整 Codex 元数据 |
| 会话归属 | 独立确认后活动/归档 JSONL 和 SQLite 全部写当前 Provider，失败时临时回滚，结束后不保留备份 |

账号匹配同时检查 Provider、Base URL 和本地 Key，优先匹配之前的活动账号；发现外部配置变化时只清除活动标记，不自动创建重复账号。当前账号编辑前的应用快照保存在私有账号库，用于区分当前配置和待应用档案。公开状态不返回快照、Key、请求头或 OAuth 凭据。切换完整替换共享 Provider 主表及子表，保留其他 Provider 和全局配置。
