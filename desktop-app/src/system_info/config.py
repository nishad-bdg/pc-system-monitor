"""Install-time config for packaged Windows builds.

Looks for KEY=VALUE files (same names as env vars) in:
1. SYSTEM_INFO_CONFIG path
2. Beside the executable (PyInstaller)
3. %APPDATA%/system-info/config.env (Windows) or ~/.config/system-info/config.env
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


CONFIG_KEYS = (
    "SYSTEM_INFO_API_URL",
    "SYSTEM_INFO_API_KEY",
    "SYSTEM_INFO_PC_NAME",
    "SYSTEM_INFO_UPDATE_URL",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def user_config_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("APPDATA") or str(Path.home())
        return Path(base) / "system-info"
    base = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "system-info"


def config_candidates() -> list[Path]:
    paths: list[Path] = []
    explicit = os.getenv("SYSTEM_INFO_CONFIG", "").strip()
    if explicit:
        paths.append(Path(explicit))
    paths.append(install_dir() / "system-info.env")
    paths.append(user_config_dir() / "config.env")
    return paths


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        value = raw.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_install_config() -> dict[str, str]:
    """Merge first found config file into process env (does not override existing env)."""
    merged: dict[str, str] = {}
    for path in config_candidates():
        if not path.is_file():
            continue
        merged = parse_env_file(path)
        break
    for key in CONFIG_KEYS:
        if key in os.environ and os.environ[key]:
            continue
        if key in merged and merged[key]:
            os.environ[key] = merged[key]
    return {k: os.environ.get(k, "") for k in CONFIG_KEYS}


def write_user_config(
    *,
    api_url: str,
    api_key: str,
    pc_name: str = "",
    update_url: str = "",
) -> Path:
    """Write %APPDATA%/system-info/config.env (used by the Windows installer)."""
    directory = user_config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.env"
    lines = [
        f"SYSTEM_INFO_API_URL={api_url}",
        f"SYSTEM_INFO_API_KEY={api_key}",
        f"SYSTEM_INFO_PC_NAME={pc_name}",
        f"SYSTEM_INFO_UPDATE_URL={update_url}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
