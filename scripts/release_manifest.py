"""Generate metadata only after the matching DMG has been built."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_version import APP_VERSION, UPDATE_REPOSITORY

artifact = Path('dist') / f'MaoLocal Codex 管理器-{APP_VERSION}-arm64.dmg'
manifest = {
    'version': APP_VERSION,
    'architecture': 'arm64',
    'url': f'https://github.com/{UPDATE_REPOSITORY}/releases/download/v{APP_VERSION}/{quote(artifact.name)}',
    'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
    'size': artifact.stat().st_size,
    'release_url': f'https://github.com/{UPDATE_REPOSITORY}/releases/tag/v{APP_VERSION}',
}
Path('dist/update.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
