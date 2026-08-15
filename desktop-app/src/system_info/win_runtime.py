"""Windows frozen-app helpers: crash log, tray AppID, single-instance mutex.

The packaged watcher is a windowed (no-console) process. Without these, a
startup crash vanishes with no log, a second launch from the installer can
fight the first, and Windows 10/11 may hide the notify icon / toasts.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from .config import user_config_dir

WATCH_MUTEX_NAME = "Local\\RGM.SystemInfoReporter.Watch"
APP_USER_MODEL_ID = "RGM.SystemInfoReporter"
_MAX_LOG_BYTES = 100_000
_mutex_handle = None


def crash_log_path() -> Path:
    return user_config_dir() / "crash.log"


def log_watch_error(
    message: str,
    exc: BaseException | None = None,
    extra: str = "",
) -> None:
    """Append a timestamped diagnostic to %APPDATA%\\system-info\\crash.log."""
    try:
        path = crash_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        parts = [time.strftime("%Y-%m-%d %H:%M:%S"), message]
        if extra:
            parts.append(extra.rstrip())
        if exc is not None:
            parts.append(
                "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ).rstrip()
            )
        body = "\n".join(parts) + "\n\n"
        if path.is_file() and path.stat().st_size > _MAX_LOG_BYTES:
            path.write_text(body, encoding="utf-8")
        else:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(body)
    except OSError:
        pass


def install_crash_handler() -> None:
    """Log unhandled exceptions for frozen Windows builds (no console)."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    previous = sys.excepthook

    def _hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        wrapped = exc if isinstance(exc, BaseException) else None
        log_watch_error("unhandled exception", wrapped, extra=text)
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "System Info Reporter stopped unexpectedly.\n\n"
                f"Details were saved to:\n{crash_log_path()}",
                "System Info Reporter",
                0x10,
            )
        except Exception:
            pass
        previous(exc_type, exc, tb)

    sys.excepthook = _hook


def set_app_user_model_id() -> None:
    """Identify this process to the Windows shell so the tray icon/toasts show."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        pass


def acquire_watch_mutex() -> bool:
    """Return False when another --watch instance is already running.

    Fail-open (return True) if the mutex APIs are unavailable so a watcher
    still starts rather than silently doing nothing.
    """
    global _mutex_handle
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, True, WATCH_MUTEX_NAME)
        already = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        if already:
            if handle:
                kernel32.CloseHandle(handle)
            return False
        _mutex_handle = handle
        return True
    except Exception:
        return True
