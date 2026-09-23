"""Public GitHub release discovery and verified installer download."""
import hashlib
import json
import platform
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from app_version import APP_VERSION, UPDATE_REPOSITORY

BASE = f'https://github.com/{UPDATE_REPOSITORY}/releases'
LOCK = threading.Lock()
MAX_SIZE = 512 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('更新版本号无效')
    return tuple(map(int, value.split('.')))


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ValueError('更新信息无效')
    version_tuple(data.get('version'))
    prefix = f"{BASE}/download/v{data['version']}/"
    url = data.get('url', '')
    if not isinstance(url, str) or not url.startswith(prefix) or not url.endswith('.dmg') or '/' in url[len(prefix):] or '?' in url or '#' in url:
        raise ValueError('安装包地址无效')
    if data.get('architecture') != 'arm64':
        raise ValueError('更新架构不匹配')
    if not isinstance(data.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', data['sha256']):
        raise ValueError('安装包校验信息无效')
    if type(data.get('size')) is not int or not 0 < data['size'] <= MAX_SIZE:
        raise ValueError('安装包大小无效')
    return data


def check_update():
    request = Request(f'{BASE}/latest/download/update.json', headers={'User-Agent': 'MaoLocal-Updater'})
    with urlopen(request, timeout=20) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('更新信息过大')
    data = validate_manifest(json.loads(raw))
    return {**data, 'current_version': APP_VERSION,
            'available': platform.machine() == 'arm64' and version_tuple(data['version']) > version_tuple(APP_VERSION)}


def download_update():
    if not LOCK.acquire(blocking=False):
        raise ValueError('正在下载更新，请稍候')
    try:
        data = check_update()
        if not data['available']:
            raise ValueError('当前没有适用的新版本')
        folder = Path(tempfile.mkdtemp(prefix='maolocal-update-'))
        target = folder / f"MaoLocal-{data['version']}.dmg"
        try:
            digest = hashlib.sha256()
            size = 0
            with urlopen(Request(data['url'], headers={'User-Agent': 'MaoLocal-Updater'}), timeout=60) as response, target.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > data['size']:
                        raise ValueError('安装包大小与发布信息不符')
                    digest.update(chunk)
                    output.write(chunk)
            if size != data['size'] or digest.hexdigest() != data['sha256']:
                raise ValueError('安装包校验失败，请重新下载')
            subprocess.run(['open', str(target)], check=True)
        except Exception:
            target.unlink(missing_ok=True)
            folder.rmdir()
            raise
        return {'version': data['version'], 'message': '安装包已打开，请退出管理器，将新版拖入 Applications 覆盖安装。'}
    finally:
        LOCK.release()
