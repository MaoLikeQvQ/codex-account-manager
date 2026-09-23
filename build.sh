#!/bin/bash
# 打包 MaoLocal Codex 管理器为 macOS .app 和拖拽安装 DMG
set -e
cd "$(dirname "$0")"

APP_NAME="MaoLocal Codex 管理器"
PROJECT_DIR="$PWD"
APP_VERSION="$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' app_version.py | head -n 1)"
APP_BUNDLE="dist/$APP_NAME.app"
DMG_NAME="MaoLocal-Codex-Manager-$APP_VERSION-arm64.dmg"
PYINSTALLER_BIN="${PYINSTALLER_BIN:-$(command -v pyinstaller || true)}"

if [ -z "$PYINSTALLER_BIN" ] && [ -x /opt/miniconda3/bin/pyinstaller ]; then
  PYINSTALLER_BIN=/opt/miniconda3/bin/pyinstaller
fi

if [ -z "$PYINSTALLER_BIN" ]; then
  echo "未找到 PyInstaller，请先执行：python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

if [ -z "$APP_VERSION" ]; then
  echo "无法从 app_version.py 读取应用版本" >&2
  exit 1
fi

echo "==> 清理旧的构建产物"
rm -rf build "dist/$APP_NAME.app" "dist/$APP_NAME"
mkdir -p dist
find dist -maxdepth 1 -type f -name "$APP_NAME-*.dmg" -delete
mkdir -p build/spec

echo "==> PyInstaller 打包（--windowed，原生窗口、无终端）"
/usr/bin/env -u OPENSSL_MODULES "$PYINSTALLER_BIN" \
  --noconfirm \
  --clean \
  --specpath build/spec \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "local.maolike.codex-manager" \
  --add-data "$PROJECT_DIR/web:web" \
  --add-data "$PROJECT_DIR/imagegen_plugin:imagegen_plugin" \
  app.py

echo "==> 写入应用版本并重新签名"
APP_PLIST="$APP_BUNDLE/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleShortVersionString -string "$APP_VERSION" "$APP_PLIST"
/usr/bin/plutil -replace CFBundleVersion -string "$APP_VERSION" "$APP_PLIST" 2>/dev/null || \
  /usr/bin/plutil -insert CFBundleVersion -string "$APP_VERSION" "$APP_PLIST"
/usr/bin/codesign --force --deep --sign - "$APP_BUNDLE"

echo "==> 创建拖拽安装 DMG"
mkdir -p build/dmg
cp -R "$APP_BUNDLE" build/dmg/
ln -s /Applications build/dmg/Applications
/usr/bin/hdiutil create \
  -volname "$APP_NAME $APP_VERSION" \
  -srcfolder build/dmg \
  -ov \
  -format UDZO \
  "dist/$DMG_NAME"

echo "==> 完成"
ls -ld "$APP_BUNDLE"
ls -lh "dist/$DMG_NAME"
