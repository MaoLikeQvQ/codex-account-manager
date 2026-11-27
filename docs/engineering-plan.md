# 项目目录与文件职责

更新：2026-11-27。本文对应已完成的本地目录整理。业务规则保持原有实现，主要变更为文件移动、导入、资源定位与构建路径适配；尚未提交或发布此次整理。

## 根目录

```text
codex-account-manager/
  app.py                   # 启动入口，调用 maox.http.server.main
  build.sh                 # 兼容构建入口，转交 scripts/build.sh
  requirements.txt         # 桌面打包依赖
  README.md
  AGENTS.md
  maox/                    # Python 功能模块
  frontend/                # React 源码及前端工程配置
  assets/                  # 应用图标等原始素材
  imagegen_plugin/         # 随应用分发的生成插件
  scripts/                 # 打包、图标和发布清单命令
  docs/                    # 项目结构、设计与历史方案
  tests/                   # 本地 Python 测试，Git 忽略
  web/                     # 前端构建输出
```

`app.py` 和 `build.sh` 只保留启动兼容用途，不在根目录承载业务。原 `DESIGN.md` 移到 `docs/design.md`。`dist/` 和 `output/` 按需生成，旧产物与旧设计方案已清理。

## 后端：maox

```text
maox/
  manager.py               # 现有管理器门面，组合跨能力流程
  version.py               # 应用版本和更新仓库
  accounts/
    service.py             # 账号档案、保存、删除与激活
    official.py            # 官方授权与账号激活
    config_import.py       # 渠道配置解析和校验
    provider_switch.py     # 保留现有配置的 Provider 更新
    models.py              # 模型发现和连接验证
    quota.py               # 官方配额读取
  history/
    service.py             # 历史扫描、归属和恢复
  usage/
    summary.py             # Token 聚合与费用计算
    pricing.py             # 价格来源、同步和缓存
    quota_estimate.py      # 剩余额度估算
  requests/
    usage.py               # 逐响应记录读取
    timing.py              # 请求计时记录和关联
    network_events.py      # 网络事件清洗、存储和查询
    timing_config.py       # OTLP 导出配置
  imagegen/
    service.py             # Custom ImageGen 配置、安装与迁移
  wakeup/
    service.py             # 唤醒规则、计划和执行协调
    http.py                # 唤醒请求
  benchmark/
    service.py             # 鹈鹕请求和结果解析
    svg.py                 # SVG 安全预览
  codex/
    restart.py             # Codex 重启状态与运行进程识别
  desktop/
    native_window.py       # 原生窗口首击处理
  updates/
    check.py               # GitHub 更新检查与下载
    install.py             # 安装校验、替换和回退
  http/
    server.py              # HTTP 接口、静态资源与服务运行
  shared/
    common.py              # 现有共享常量、路径和类型
    storage.py             # 现有文件、TOML、备份与批量提交
```

第一轮保留已有 Mixin 组合和模块内逻辑，避免把目录迁移与业务重构混合。原 `manager_parts/` 和根目录的管理器、版本、更新、原生窗口实现均已迁入对应能力目录，不保留旧模块占位副本。

## 前端：frontend/src

```text
frontend/src/
  main.tsx
  vite-env.d.ts
  app/
    App.tsx
    WorkspaceShell.tsx
    useManager.ts
  features/
    accounts/              # 列表、卡片、配额与账号表单
    overview/              # 总览页面与 UsageSummary
    usage/                 # UsagePage
    requests/              # 请求页面、网络事件与 useRequests
    tools/                 # 图片配置、唤醒与鹈鹕工具
  shared/
    api/client.ts          # HTTP 请求与通用错误
    lib/format.ts          # 金额与 Token 格式化
    lib/date.ts            # 通用日期
    ui/                    # 通用对话框与面板样式
    usage/                 # Token 展示和时间范围选择
    theme.ts
    types.ts               # 现有统一类型契约
```

原 `Dashboard.tsx` 的 `Overview` 与 `UsagePanel` 分别归为 `overview/UsageSummary.tsx` 和 `usage/UsagePage.tsx`；公共样式移入 `shared/ui/panelStyles.ts`。原 `api.ts` 的请求与格式化职责分别归位。

## 本地测试

Python 测试位于 `tests/accounts`、`history`、`usage`、`requests`、`tools`、`desktop`、`updates`、`http`，通用夹具位于 `tests/support.py`。前端测试保留 `frontend/tests/` 和本机 Playwright 配置。

所有测试、夹具和结果均由 Git 忽略。根目录执行以下命令仍可发现本地 Python 测试；缺少本地测试时不能把零用例当作验收成功。

```bash
python3 -m unittest discover -q
npm --prefix frontend run build
PLAYWRIGHT_CHROMIUM_CHANNEL=chrome npm --prefix frontend test
```

## 维护规则

- 新代码先归对应能力目录；只有跨能力且不含业务规则的代码才放入 shared。
- app 组合业务页面，shared 不导入页面；后端基础模块不反向导入 HTTP Handler。
- 以文件职责为依据决定拆分，不创建空服务或大量单函数包装文件。
- 手写文件不超过 1000 行。图片插件 bundle 必须由独立源码工程构建，不手工拆改。
- 源码资源从项目根定位，打包资源从 PyInstaller 资源根定位；移动文件时必须同时验证两者。
- 账号、认证、历史及图片配置继续使用原用户目录，代码整理不迁移真实数据。

后续可按实际修改继续拆分 history 的 JSONL/SQLite 职责、账号存储与业务规则、HTTP 路由，以及 shared 中混合的基础能力。这些属于后续职责重构，不是本轮目录整理已完成的内容。
