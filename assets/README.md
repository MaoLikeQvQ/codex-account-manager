# MaoX 图标

- `maox-icon.svg`：1024 × 1024 的应用图标源文件，透明画布、石墨黑圆角底、浅白色 Code 字标与薄荷绿终端光标。Dock、应用及网页小图标、页面左上角共用这个文件。
- `maox-mark.svg`：24 × 24 的单色标识，使用 `currentColor`，适合单色或菜单栏小尺寸。

`build.sh` 通过 `scripts/build_icon.swift` 使用 macOS AppKit 渲染 SVG，输出 16–1024 px 的 PNG 表示，再用 `iconutil` 生成 ICNS 并交给 PyInstaller。打包图标不依赖图片下载或额外图像库。

应用当前没有菜单栏托盘功能；单色源文件仅为可复用图形，不会新增托盘入口。
