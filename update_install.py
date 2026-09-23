"""Stage a verified macOS bundle, then replace it after this process exits."""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE_ID = 'local.maolike.codex-manager'


def installed_bundle():
    if not getattr(sys, 'frozen', False):
        raise ValueError('源码运行不支持自动安装，请使用已安装的应用版本')
    bundle = Path(sys.executable).resolve().parents[2]
    if bundle.suffix != '.app' or str(bundle).startswith('/Volumes/'):
        raise ValueError('请先将应用安装到 Applications 后再更新')
    if not os.access(bundle.parent, os.W_OK):
        raise ValueError('应用目录不可写，请将应用移到当前用户的 Applications 文件夹')
    return bundle


def verify_bundle(bundle, version):
    with (bundle / 'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleShortVersionString') != version:
        raise ValueError('安装包应用标识或版本不匹配')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)], check=True, capture_output=True)


# All paths are positional arguments, never interpolated into shell code.
INSTALL_SCRIPT = '''#!/bin/bash
set -eu
pid="$1"; current="$2"; staged="$3"; backup="$4"; work="$5"
for ((i=0; i<120; i++)); do
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then
  echo 'Update cancelled: application did not exit' >&2
  exit 1
fi
moved=0
rollback() {
  if [ "$moved" = 1 ]; then
    if [ -e "$current" ]; then mv "$current" "$work/failed.app"; fi
    mv "$backup" "$current"
    /usr/bin/open "$current" || true
  fi
}
trap rollback ERR
mv "$current" "$backup"
moved=1
mv "$staged" "$current"
/usr/bin/open "$current"
trap - ERR
rm -rf "$backup"
rm -rf "$work"
'''


def prepare_install(dmg, version, current):
    work = Path(tempfile.mkdtemp(prefix='.maolocal-update-', dir=current.parent))
    mount = work / 'mount'
    mount.mkdir()
    staged = work / current.name
    attached = False
    try:
        subprocess.run(['/usr/bin/hdiutil', 'attach', str(dmg), '-readonly', '-nobrowse', '-mountpoint', str(mount)], check=True, capture_output=True)
        attached = True
        candidates = list(mount.glob('*.app'))
        if len(candidates) != 1:
            raise ValueError('安装包必须包含一个应用')
        verify_bundle(candidates[0], version)
        subprocess.run(['/usr/bin/ditto', str(candidates[0]), str(staged)], check=True, capture_output=True)
        verify_bundle(staged, version)
    except Exception:
        if attached:
            subprocess.run(['/usr/bin/hdiutil', 'detach', str(mount)], capture_output=True)
        shutil.rmtree(work)
        raise
    subprocess.run(['/usr/bin/hdiutil', 'detach', str(mount)], check=True, capture_output=True)
    script = work / 'install.sh'
    script.write_text(INSTALL_SCRIPT)
    log_dir = Path.home() / 'Library/Logs/MaoLocal-Codex-Manager'
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / 'update.log').open('w') as log:
        subprocess.Popen(['/bin/bash', str(script), str(os.getpid()), str(current), str(staged), str(work / 'previous.app'), str(work)], stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
