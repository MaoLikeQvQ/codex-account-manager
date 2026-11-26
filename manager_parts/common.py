from __future__ import annotations

import copy
import hashlib
import json
import os
import plistlib
import re
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import tomllib


STORE_VERSION = 8
MAX_SESSION_META_BYTES = 4 * 1024 * 1024
OFFICIAL_PROVIDER_ID = "openai"
CUSTOM_PROVIDER_ID = "MaoLocal"
OFFICIAL_LOGIN_TIMEOUT_SECONDS = 5 * 60
IMAGE_PLUGIN_VERSION = "0.2.0"
CODEX_APP = Path("/Applications/ChatGPT.app")
def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Paths:
    codex_home: Path
    app_home: Path

    @classmethod
    def from_environment(cls) -> "Paths":
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        app_home = Path(
            os.environ.get("MAOLIKE_CODEX_HOME", Path.home() / ".maolike" / "codex")
        )
        return cls(codex_home.expanduser().resolve(), app_home.expanduser().resolve())

    @property
    def config(self) -> Path:
        return self.codex_home / "config.toml"

    @property
    def auth(self) -> Path:
        return self.codex_home / "auth.json"

    @property
    def accounts(self) -> Path:
        return self.app_home / "codex_accounts.json"

    @property
    def bundled_model_catalog(self) -> Path:
        return self.app_home / "bundled-model-catalog.json"

    @property
    def backups(self) -> Path:
        return self.app_home / "backups"

    @property
    def history_state(self) -> Path:
        return self.app_home / "history_state.json"

    @property
    def image_config(self) -> Path:
        return self.app_home / "custom-imagegen.json"

    @property
    def image_state(self) -> Path:
        return self.app_home / "custom-imagegen-state.json"

    @property
    def image_skill(self) -> Path:
        return self.codex_home / "skills" / "maolocal-imagegen" / "SKILL.md"

    @property
    def image_plugin_dir(self) -> Path:
        return self.app_home / "imagegen_plugin"

    @property
    def image_server(self) -> Path:
        return self.image_plugin_dir / "server.cjs"

    @property
    def image_plugin_version(self) -> Path:
        return self.image_plugin_dir / "VERSION"

    @property
    def image_plugin_notices(self) -> Path:
        return self.image_plugin_dir / "THIRD_PARTY_NOTICES.txt"


@dataclass(frozen=True)
class RolloutRecord:
    path: Path
    archived: bool
    thread_id: str
    provider_id: str | None
    provider_ids: tuple[str | None, ...]
    size: int
    inode: int
    mode: int
    atime_ns: int
    mtime_ns: int
    has_encrypted_content: bool
