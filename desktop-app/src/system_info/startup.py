"""Windows startup registration (auto-run at logon) for packaged builds.

On the first run after install the app registers itself under the current
user's Run key so `system-info.exe --heartbeat` runs once at every logon —
the PC shows as online immediately, before the next scheduled heartbeat.

A marker file in the app config directory records that registration already
happened, so later runs skip it. The installer removes both the Run value and
the marker on uninstall.

Every run is guarded by SYSTEM_INFO_NO_STARTUP=1 for manual/portable use.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import is_frozen, user_config_dir

try:
    import winreg as _winreg
except ImportError:  # pragma: no cover - not on macOS
    _winreg = None

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "SystemInfoReporter"
MARKER = "startup-registered"


def is_supported() -> bool:
    """Only meaningful on Windows for a frozen (installed/updated) build."""
    return os.name == "nt" and is_frozen()


def startup_command() -> str:
    """Command line stored in the Run key: '<exe>' --heartbeat."""
    exe = str(sys.executable)
    return f'"{exe}" --heartbeat'


def _marker_path() -> Path:
    return user_config_dir() / MARKER


def already_registered() -> bool:
    if not is_supported():
        return False
    return _marker_path().is_file()


def register_startup() -> bool:
    """Add the HKCU Run entry once (first run) and write the marker. Idempotent."""
    if not is_supported() or _winreg is None:
        return False
    if already_registered():
        return True
    try:
        with _winreg.OpenKey(
            _winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            _winreg.KEY_SET_VALUE,
        ) as key:
            _winreg.SetValueEx(
                key, RUN_VALUE_NAME, 0, _winreg.REG_SZ, startup_command()
            )
        marker = _marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        return True
    except OSError:
        return False


def unregister_startup() -> bool:
    """Remove the Run value + marker (called on uninstall/portable runs)."""
    removed = False
    if _winreg is not None:
        try:
            with _winreg.OpenKey(
                _winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                _winreg.KEY_SET_VALUE,
            ) as key:
                _winreg.DeleteValue(key, RUN_VALUE_NAME)
            removed = True
        except OSError:
            pass
    try:
        _marker_path().unlink(missing_ok=True)
    except OSError:
        pass
    return removed