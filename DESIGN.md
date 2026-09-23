# MaoLocal Codex 管理器 — v2 设计

## 目标

提供四条可验证闭环：

- 官方账号切换：隔离 CODEX_HOME 发起 ChatGPT 设备码 OAuth → 保存独立凭据档案 → 验证并可回滚切换 auth/config → 使用 Codex 内置模型目录。
- 渠道账号切换：验证目标账号 → 读取目标渠道模型 → 原子替换 config/auth/catalog → 失败时整组回滚 → 标记活动账号。
- 模型注入：渠道多地址模型发现 → Codex catalog 元数据补全 → `model_catalog_json` → 原生目录筛选或旧版补丁 → 启动或重启 Codex。
- 历史归属：扫描全部 rollout → 创建操作内临时回滚副本 → 只改 session_meta → 事务更新 SQLite → 删除临时副本 → 全量复核。

Sub2API 只扩展渠道账号连接参数，不分叉模型注入和历史归属实现。

主流程采用渐进披露：新增 Sub2API 默认使用兼容模式 + HTTP/SSE，只展示名称、Provider ID、Base URL、Key 和默认模型；API Key Mode/WebSocket 仍由高级连接参数提供，已有非默认账号编辑时自动展开。

## 界面结构

导航固定为首页、账号、模型、工具四个页面。桌面窗口按 3:2 比例布局，首页显示当前 Provider 的可按时间筛选的 token 用量。账号列表点击只查看，切换、编辑与验证是独立操作。全局启动按钮只使用已保存配置。

模型页的默认模型和目录勾选统一暂存；应用时复用 post-switch 模型目录/补丁接口，再调用 models/select。它不是跨接口事务，部分失败必须明确提示，保留草稿供重试。官方账号不走渠道补丁。新增账号仍保留既有默认模型和推理强度字段，以兼容账号保存契约。

工具页各项单独确认并保留执行结果。图片工具把保存请求参数的“配置”和执行版本比较、插件安装更新及 MCP 写入的“应用”分开；官方模型目录恢复仅放在模型页。

## 模块

```text
app.py             本地 HTTP API、窗口入口、启动时同步
codex_manager.py   对外管理器入口、状态、Codex App 启动和旧版补丁
manager_parts/     账号、官方登录、模型、图片、历史、存储、用量模块
web/               无框架 WebView 界面
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
- `provider_id` 是模型 Provider 和会话归属的稳定键；编辑、迁移或显示名称变化均不能隐式更换它。
- Sub2API API Key Mode 的 Key 继续写入 `auth.json`，不使用 `experimental_bearer_token`，避免密钥进入 `config.toml` 及其备份。
- WebSocket 模式只确保全局功能为 `true`；Provider 不再写入 `supports_websockets`，HTTP/SSE 也不反向关闭用户已有的全局功能。

## 写入不变量

1. 远端模型列表为空或请求失败时，不改写现有 catalog。
2. catalog 使用临时文件 + `fsync` + `os.replace` 原子提交。
3. 账号切换前备份 `config.toml`、`auth.json` 和 catalog。
4. catalog 只包含当前渠道返回的模型，已下线模型不会无限累积。
5. 已知 Codex 模型复用 bundled 元数据；未知模型克隆兼容模板后覆盖 slug、显示名和目录字段。
6. Web 状态不包含 API Key 或官方 OAuth 令牌。
7. 普通账号事务不改对话；历史归属由独立、显式确认的 API 执行。
8. 历史归属覆盖同一 rollout 中的全部 `session_meta`，其他 JSONL 行保持原字节。
9. SQLite 使用事务，任一数据库失败时使用操作内临时副本恢复已提交数据库和 rollout；结束后不保留历史归属备份。
10. 扫描结果按 inode、大小和 mtime 缓存；写入前强制重扫以防并发变化。
11. 账号切换中的 config、auth、catalog、同步状态和活动账号任一写入失败时，恢复切换前快照。
12. 修改 Codex App 前先完整退出运行进程；模型筛选补丁必须唯一识别原始、`2.6.2` 错误或当前正确状态。
13. 旧版 Codex 的自定义 Provider 桌面模型菜单由补丁按本地 catalog 的 `visibility` 展示，`additionalAvailableModels` 只允许补充官方 Provider；新版若原生支持已配置 catalog，则不修改 App，沿用其筛选规则。旧注入状态必须可原位迁移。
14. Sub2API 与普通兼容渠道共用 catalog、目录筛选校验、切换事务和会话归属实现；兼容层不得复制这些业务流程。
15. Sub2API 的公开状态只暴露连接类型、鉴权模式与传输模式，不暴露 API Key、Authorization、actor header 之外的凭据或官方 OAuth token。
16. v7 → v8 迁移前备份账号库，并原样保留活动账号、`provider_id`、Key、模型选择与 Provider 配置。
17. 图片工具通过独立 MCP 安装，不修改 Codex 图片功能门禁或 CLI 鉴权逻辑；Key 只进入权限为 `0600` 的专用配置。
18. 官方 ChatGPT OAuth token 不作为 Platform 图片 API 凭据；选择已管理官方账号时，只用于 Codex 官方 Responses 图片链路。
19. 模型发现按 Base URL 原地址、`/models`、`/v1/models` 去重尝试；均失败时使用 Codex 内置官方目录，不向 OpenAI 转发第三方 Key。
20. 图片配置与应用分离；应用先比较版本，只在插件不是当前版本时更新运行时文件，然后写入 MCP 配置。
21. 内置模型目录缓存随 Codex 二进制变化失效；启动自定义账号时只从当前安装补入新增官方模型并校验补丁，不隐式请求渠道接口或覆盖渠道模型显示选择。

## API

- `GET /api/state`
- `GET /api/usage?period=today|yesterday|7d|date&date=YYYY-MM-DD`（只读汇总当前 Provider 的所选时间 token 与官方价估算）
- `POST /api/models/preview`（只读获取当前渠道候选模型）
- `POST /api/accounts/save`
- `POST /api/accounts/verify`（只读校验渠道登录，不落库、不切换）
- `POST /api/accounts/official-login/start`
- `GET /api/accounts/official-login/status?login_id=<login_id>`
- `POST /api/accounts/official-login/complete`
- `POST /api/accounts/official-login/cancel`
- `POST /api/accounts/delete`
- `POST /api/accounts/activate`
- `POST /api/accounts/post-switch`（显式执行模型注入或历史归属）
- `POST /api/models/sync`（可传 `model_ids`，只写入通过远端目录校验的选中模型）
- `POST /api/models/select`
- `POST /api/codex/sync-launch`
- `POST /api/image-generation/configure`
- `POST /api/image-generation/apply`
- `POST /api/history/claim-all`

所有修改请求串行执行，避免同步、账号切换和模型选择互相覆盖。

图片 MCP 的凭据来源独立于当前活动账号。`managed_account` 只在图片配置中保存账号库路径与账号名；运行时每次读取指定账号。官方账号使用保存的 ChatGPT OAuth access token 和 account ID 请求 Codex Responses SSE，绝不将 OAuth token 投递到 Platform `/v1/images`；自定义账号和自定义链接继续使用 Images/Responses 兼容接口。任何图片请求都不自动重试。

## Sub2API 回归矩阵

| 场景 | 最低验证 |
| --- | --- |
| 兼容模式 | `requires_openai_auth = true`、HTTP/SSE 默认关闭 WebSocket、`auth.json` 写 Key |
| API Key Mode | `requires_openai_auth = false`、actor header 存在、Key 不进入 config/public state/sync state |
| WebSocket | Provider 支持 WebSocket、全局 v2 feature 为 true、其他 `[features]`/MCP 配置保持 |
| 模型发现 | 同时接受 `data[*].id` 与 `models[*].slug` |
| 模型注入 | 仍生成本地 catalog、保留隐藏选择；新版使用原生筛选，旧版调用补丁 |
| 会话归属 | 活动/归档 JSONL 和 SQLite 全部写稳定 `provider_id`，失败时临时回滚，结束后不保留备份 |
