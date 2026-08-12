"""Release-based auto-update (Windows-friendly).

Expects SYSTEM_INFO_UPDATE_URL to point at a JSON manifest:

{
  "version": "0.2.0",
  "windows": {
    "url": "https://example.com/releases/system-info-0.2.0.exe",
    "sha256": "optional-hex-digest"
  }
}
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import requests

from .version import __version__
from .config import install_dir, is_frozen

UPDATE_TIMEOUT = 15


def _parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _parse_version(remote) > _parse_version(local)


def fetch_manifest(update_url: str) -> dict | None:
    try:
        resp = requests.get(update_url, timeout=UPDATE_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def check_for_update(update_url: str | None = None) -> dict | None:
    """Return manifest if a newer Windows build is available, else None."""
    url = (update_url or os.getenv("SYSTEM_INFO_UPDATE_URL") or "").strip()
    if not url:
        return None
    manifest = fetch_manifest(url)
    if not manifest:
        return None
    remote_version = str(manifest.get("version") or "")
    if not remote_version or not is_newer(remote_version):
        return None
    windows = manifest.get("windows")
    if not isinstance(windows, dict) or not windows.get("url"):
        return None
    return manifest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_windows_update(manifest: dict) -> str | None:
    """Download new exe beside the current one and write an updater batch.

    Returns path to the pending updater script, or None on failure.
    The batch replaces the running exe on the next scheduled run-friendly
    restart (user or Task Scheduler).
    """
    if not is_frozen() or os.name != "nt":
        return None
    windows = manifest.get("windows")
    if not isinstance(windows, dict):
        return None
    url = str(windows.get("url") or "")
    expected = str(windows.get("sha256") or "").lower().strip()
    if not url:
        return None

    current = Path(sys.executable).resolve()
    target_dir = install_dir()
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
    except (requests.RequestException, OSError):
        return None

    suffix = current.suffix or ".exe"
    pending = target_dir / f"system-info.new{suffix}"
    try:
        with pending.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        if expected:
            actual = _sha256_file(pending)
            if actual.lower() != expected:
                pending.unlink(missing_ok=True)
                return None
    except OSError:
        return None

    # Batch: wait briefly, replace exe, delete pending, optional restart not required
    # for Task Scheduler — next 30m run uses the new binary.
    updater = target_dir / "apply-update.cmd"
    backup = target_dir / f"system-info.prev{suffix}"
    script = f"""@echo off
ping 127.0.0.1 -n 3 >nul
if exist "{backup}" del /f /q "{backup}"
if exist "{current}" move /y "{current}" "{backup}"
move /y "{pending}" "{current}"
del /f /q "%~f0"
"""
    try:
        updater.write_text(script, encoding="utf-8")
    except OSError:
        return None
    try:
        import subprocess

        flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            flags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(updater)],
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return str(updater)
    return str(updater)


def maybe_auto_update(quiet: bool = True) -> bool:
    """Check manifest and start Windows update if newer. Returns True if started."""
    manifest = check_for_update()
    if not manifest:
        return False
    path = apply_windows_update(manifest)
    if path and not quiet:
        print(f"[update] applying {manifest.get('version')} via {path}")
    return bool(path)
