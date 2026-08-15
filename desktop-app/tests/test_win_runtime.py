import sys
import types

from system_info.win_runtime import (
    WATCH_MUTEX_NAME,
    acquire_watch_mutex,
    crash_log_path,
    install_crash_handler,
    log_watch_error,
    set_app_user_model_id,
)


def _install_fake_ctypes(monkeypatch, kernel32):
    fake = types.ModuleType("ctypes")
    fake.windll = types.SimpleNamespace(kernel32=kernel32)
    monkeypatch.setitem(sys.modules, "ctypes", fake)
    return fake


def test_acquire_watch_mutex_non_windows():
    assert acquire_watch_mutex() is True


def test_acquire_watch_mutex_already_running(monkeypatch):
    closed = {}

    class Kernel:
        def CreateMutexW(self, *a):
            return 7

        def GetLastError(self):
            return 183

        def CloseHandle(self, handle):
            closed["handle"] = handle

    monkeypatch.setattr("system_info.win_runtime.os.name", "nt")
    _install_fake_ctypes(monkeypatch, Kernel())
    assert acquire_watch_mutex() is False
    assert closed["handle"] == 7


def test_acquire_watch_mutex_fail_open(monkeypatch):
    class Kernel:
        def CreateMutexW(self, *a):
            raise OSError("no mutex")

    monkeypatch.setattr("system_info.win_runtime.os.name", "nt")
    _install_fake_ctypes(monkeypatch, Kernel())
    assert acquire_watch_mutex() is True


def test_log_watch_error_writes_crash_log(tmp_path, monkeypatch):
    monkeypatch.setattr("system_info.win_runtime.user_config_dir", lambda: tmp_path)
    log_watch_error("tray failed", RuntimeError("win32"))
    text = (tmp_path / "crash.log").read_text(encoding="utf-8")
    assert "tray failed" in text
    assert "win32" in text
    assert crash_log_path() == tmp_path / "crash.log"


def test_install_crash_handler_skips_unfrozen(monkeypatch):
    monkeypatch.setattr("system_info.win_runtime.os.name", "nt")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    before = sys.excepthook
    install_crash_handler()
    assert sys.excepthook is before


def test_set_app_user_model_id_noop_off_windows():
    set_app_user_model_id()
    assert WATCH_MUTEX_NAME.startswith("Local\\")
