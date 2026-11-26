# 桌面主题与交互 Implementation Plan

**Goal:** 重做常规浅色/暗色主题、修复原生交互并交付本地应用包。
**Architecture:** theme.ts 统一组件状态；WorkspaceShell.tsx 管理导航与工具栏；现有面板保留业务；原生修复以隔离探针证据为准。
**Spec:** docs/superpowers/specs/2026-10-26-desktop-redesign.md

- [x] 交互诊断：隔离原生窗口复现一次点击、弹窗持久性；按根因补回归并修复。
- [x] 主题与外壳：统一蓝色强调、浅灰/深灰表面、侧栏、排版与控件；保留主题记忆与所有入口。
- [x] 验证：生产构建、Chromium/WebKit 回归、浅/暗/窄窗口截图、原生点击与弹窗验证、Python 回归。
- [x] 文档与打包：更新设计说明，运行 build.sh，校验 .app 签名、DMG 与本地文件，不安装和发布。

重点：异步刷新不能卸载弹窗；菜单/Tooltip 不吞首次点击；嵌套弹窗不能关闭底层编辑；主题切换不重建业务状态；打包产物须包含当前生产资源。

## 验证结果

- 已通过真实原生双窗口测试复现：失焦窗口首击只激活，网页收不到事件；注册系统签名的 acceptsFirstMouse 后，首击直接执行按钮动作。9 次真实单击对应 9 组 DOM 事件，没有 dblclick。使用隔离 API 与临时账号目录。
- 遮罩点击关闭表单的回归先 RED 后 GREEN；ManagerDialog 统一忽略 backdropClick，关闭、取消和 Escape 仍可操作。无操作等待时未复现自动关闭，不将其描述为已定位的定时器问题。
- `PLAYWRIGHT_CHROMIUM_CHANNEL=chrome npm --prefix frontend test`：Chromium 19 项、WebKit 19 项全部通过。截图禁用过渡动画，验证生产资源与原有 CSP。
- `python3 -m unittest discover -q`：109 项，通过，因该解释器缺少 pywebview 跳过 1 项。`.venv/bin/python -m unittest discover -q`：109 项全部通过，含真实 WKWebView 原生回归。仍有既有 ResourceWarning。
- `bash build.sh`：成功生成 Apple Silicon `.app` 与 DMG。`codesign --verify --deep --strict` 和 `hdiutil verify` 通过。Vite 仍有单 chunk 超过 500KB 的非阻塞提示。
- 新包启动验收：直接运行本轮生成的 `.app`，隔离 CODEX_HOME 和 MAOLIKE_CODEX_HOME；API 确认空账号。通过系统辅助功能操作验证单击账号页、打开弹窗、切兼容渠道、误点遮罩不关闭、明确关闭和深色切换。验收进程已退出。
- 没有替换已安装应用、提交、推送或发布。
