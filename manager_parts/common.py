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


CATALOG_NAME = "models.json"
RESTORED_OFFICIAL_MODEL_IDS = (
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-6-astra",
    "gpt-6-luna",
    "gpt-6-sol",
)
STORE_VERSION = 8
MAX_SESSION_META_BYTES = 4 * 1024 * 1024
OFFICIAL_PROVIDER_ID = "openai"
OFFICIAL_LOGIN_TIMEOUT_SECONDS = 5 * 60
IMAGE_PLUGIN_VERSION = "0.2.0"
CODEX_APP = Path("/Applications/ChatGPT.app")
CODEX_OFFICIAL_TEAM_ID = "2DC432GLL2"
CODEX_SPARKLE_RELATIVE_PATH = Path("Contents/Frameworks/Sparkle.framework")
CODEX_SPARKLE_SIGN_TARGETS = (
    (Path("Versions/B/XPCServices/Installer.xpc"), False),
    (Path("Versions/B/XPCServices/Downloader.xpc"), True),
    (Path("Versions/B/Autoupdate"), False),
    (Path("Versions/B/Updater.app"), False),
    (Path("."), False),
)
CODEX_MODEL_FILTER_MARKER = b"maolocal-models"
CODEX_MODEL_FILTER_CONTEXT = (
    rb"additionalAvailableModels:(?P<additional>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"authMethod:(?P<auth>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"availableModels:(?P<available>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"isCustomModelProvider:(?P<custom>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"model:(?P<model>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"useHiddenModels:(?P<use_hidden>[A-Za-z_$][A-Za-z0-9_$]*)"
    rb"\}\)\{return "
)
CODEX_MODEL_FILTER_SUFFIX = (
    rb"\|\|(?P=model)\.model!==`codex-auto-review`&&\("
)
CODEX_MODEL_FILTER_TERNARY_SUFFIX = (
    rb"\?(?P=available)\.has\((?P=model)\.model\):!(?P=model)\.hidden"
)
CODEX_MODEL_FILTER_PATTERN = re.compile(
    CODEX_MODEL_FILTER_CONTEXT
    + rb"(?P<additional_condition>(?P=additional)\?\.has\((?P=model)\.model\)===!0)"
    + CODEX_MODEL_FILTER_SUFFIX
    + rb"(?P<condition>(?P=use_hidden)&&!(?P=custom)&&(?P=auth)!==`amazonBedrock`)"
    + CODEX_MODEL_FILTER_TERNARY_SUFFIX
)
CODEX_MODEL_FILTER_BROKEN_262_PATTERN = re.compile(
    CODEX_MODEL_FILTER_CONTEXT
    + rb"(?P<additional_condition>(?P=additional)\?\.has\((?P=model)\.model\)===!0)"
    + CODEX_MODEL_FILTER_SUFFIX
    + rb"(?P<condition>(?P=use_hidden)&&!!1/\*maolocal-models_*\*/)"
    + CODEX_MODEL_FILTER_TERNARY_SUFFIX
)
CODEX_MODEL_FILTER_LEGACY_PATCHED_PATTERN = re.compile(
    CODEX_MODEL_FILTER_CONTEXT
    + rb"(?P<additional_condition>(?P=additional)\?\.has\((?P=model)\.model\)===!0)"
    + CODEX_MODEL_FILTER_SUFFIX
    + rb"(?P<condition>!1/\*maolocal-models_*\*/)"
    + CODEX_MODEL_FILTER_TERNARY_SUFFIX
)
CODEX_MODEL_FILTER_PATCHED_PATTERN = re.compile(
    CODEX_MODEL_FILTER_CONTEXT
    + rb"(?P<additional_condition>!(?P=custom)&&(?P=additional)\?\.has\("
    rb"(?P=model)\.model\) +)"
    + CODEX_MODEL_FILTER_SUFFIX
    + rb"(?P<condition>!1/\*maolocal-models_*\*/)"
    + CODEX_MODEL_FILTER_TERNARY_SUFFIX
)
CODEX_MODEL_NATIVE_CATALOG_PATTERN = re.compile(
    rb"additionalAvailableModels:(?P<additional>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"authMethod:(?P<auth>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"availableModels:(?P<available>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"hasConfiguredModelCatalog:(?P<configured>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"isCustomModelProvider:(?P<custom>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"model:(?P<model>[A-Za-z_$][A-Za-z0-9_$]*),"
    rb"useHiddenModels:(?P<use_hidden>[A-Za-z_$][A-Za-z0-9_$]*)"
    rb"\}\)\{return (?P=additional)\?\.has\((?P=model)\.model\)===!0\|\|"
    rb"(?P=model)\.model!==`codex-auto-review`&&\("
    rb"(?P=configured)&&!(?P=model)\.hidden\|\|\("
    rb"(?P=use_hidden)&&!(?P=custom)&&(?P=auth)!==`amazonBedrock`"
    rb"\?(?P=available)\.has\((?P=model)\.model\):!(?P=model)\.hidden\)\)"
)
CODEX_MODEL_ANNOUNCEMENT_PATTERN = re.compile(
    rb"showAnnouncement:(?P<condition>[A-Za-z_$][A-Za-z0-9_$]*"
    rb"&&![A-Za-z_$][A-Za-z0-9_$]*)"
)
CODEX_MODEL_ANNOUNCEMENT_PATCHED_PATTERN = re.compile(rb"showAnnouncement:!1 +")


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
    def catalog(self) -> Path:
        return self.codex_home / CATALOG_NAME

    @property
    def accounts(self) -> Path:
        return self.app_home / "codex_accounts.json"

    @property
    def sync_state(self) -> Path:
        return self.app_home / "sync_state.json"

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


