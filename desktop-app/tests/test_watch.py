import argparse
import os
import sys

import pytest

from system_info.watch import HEARTBEAT_INTERVAL, HOUR_INTERVAL, WatchLoop


def _args(**overrides) -> argparse.Namespace:
    base = argparse.Namespace(
        heartbeat=False,
        print_jobs=False,
        os=False,
        ip=False,
        geo=False,
        sys=False,
        disk=False,
        printers=False,
        network=False,
        security=False,
        health=False,
        emails=False,
        no_save=False,
        json=False,
        watch=False,
        api_url="http://x",
        api_key="sk-key",
        pc_name="",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_watch_args_forces_flags_off():
    args = _args(os=True, sys=True, no_save=True, json=True, watch=True, printers=True)
    w = _args()
    from system_info.watch import watch_args

    clean = watch_args(args)
    for name in (
        "heartbeat",
        "print_jobs",
        "os",
        "ip",
        "geo",
        "sys",
        "disk",
        "printers",
        "network",
        "security",
        "health",
        "emails",
        "no_save",
        "json",
        "watch",
    ):
        assert getattr(clean, name) is False, name
    assert clean.api_url == "http://x"
    assert clean.pc_name == ""


def test_watch_args_preserves_connection_settings():
    from system_info.watch import watch_args

    clean = watch_args(_args(api_url="https://api.example.com", api_key="sk-1", pc_name="PC-1"))
    assert clean.api_url == "https://api.example.com"
    assert clean.api_key == "sk-1"
    assert clean.pc_name == "PC-1"


def test_should_full_report_hourly_aligned():
    loop = WatchLoop(_args())
    start = loop._last_full
    # Just started → next report is a full hour later.
    assert loop.should_full_report(start + 1.0) is False
    assert loop.should_full_report(start + HOUR_INTERVAL - 10) is False
    assert loop.should_full_report(start + HOUR_INTERVAL) is True
    # Then the cycle repeats.
    assert loop.should_full_report(start + HOUR_INTERVAL + 10) is False
    assert loop.should_full_report(start + HOUR_INTERVAL * 2) is True


def test_heartbeat_and_full_report_intervals_are_sane():
    # Heartbeat must be well under the dashboard/API online timeout (300s)
    # or a running watcher is shown as offline between beats.
    assert HEARTBEAT_INTERVAL <= 60
    assert HEARTBEAT_INTERVAL * 2 < 300
    assert HOUR_INTERVAL == 3600


@pytest.mark.parametrize(
    "manifest, staged, expected_fragment",
    [
        (None, None, "Already up to date"),
        ({"version": "9.9.9"}, "/x/apply-update-restart.cmd", "restart"),
        ({"version": "9.9.9"}, None, "could not be applied"),
    ],
)
def test_handle_update_request(monkeypatch, manifest, staged, expected_fragment):
    import system_info.update as update_mod

    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: manifest)
    monkeypatch.setattr(update_mod, "apply_update_and_restart", lambda *a, **k: staged)

    loop = WatchLoop(_args())
    message, title = loop.handle_update_request()

    assert expected_fragment.lower() in message.lower()
    if not manifest:
        assert "no update" in title
        assert getattr(loop, "_exit_for_update", False) is False
    elif staged:
        assert "system tray" in message.lower()
        assert loop._exit_for_update is True
        assert "update ready" in title
    else:
        assert getattr(loop, "_exit_for_update", False) is False


def test_handle_update_request_handles_exceptions(monkeypatch):
    import system_info.update as update_mod

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(update_mod, "check_for_update", boom)

    loop = WatchLoop(_args())
    message, title = loop.handle_update_request()

    assert "failed" in message.lower()
    assert "update failed" in title


def test_restart_command_non_frozen(monkeypatch):
    import sys as _sys

    monkeypatch.setattr("system_info.config.is_frozen", lambda: False)
    loop = WatchLoop(_args(pc_name="PC"))
    cmd = loop.restart_command()
    assert cmd[:3] == [_sys.executable, "-m", "system_info"]
    assert cmd[3] == "--watch"
    assert "--pc-name" in cmd and cmd[cmd.index("--pc-name") + 1] == "PC"


def test_restart_command_frozen(monkeypatch):
    monkeypatch.setattr("system_info.config.is_frozen", lambda: True)
    loop = WatchLoop(_args(pc_name=""))
    cmd = loop.restart_command()
    assert cmd == [os.path.abspath(sys.executable), "--watch"]


def test_restart_command_never_leaks_credentials(monkeypatch):
    monkeypatch.setattr("system_info.config.is_frozen", lambda: False)
    loop = WatchLoop(_args(api_url="http://x", api_key="sk-secret", pc_name="PC"))
    cmd = " ".join(loop.restart_command())
    assert "sk-secret" not in cmd
    assert "http://x" not in cmd


def test_restart_command_omits_empty_pc_name():
    loop = WatchLoop(_args())
    cmd = loop.restart_command()
    assert "--pc-name" not in cmd


def test_handle_restart_spawns_detached(monkeypatch):
    import subprocess

    spawned = {}

    def fake_popen(cmd, **kwargs):
        spawned["cmd"] = cmd
        spawned["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    loop = WatchLoop(_args(pc_name="PC-7"))
    assert loop.handle_restart() is True
    assert "--watch" in spawned["cmd"]
    assert spawned["kwargs"]["start_new_session"] is True


def test_tray_icon_shows_product_name(monkeypatch):
    import types

    from system_info.version import PRODUCT_NAME
    from system_info.watch import _tray_icon

    created = {}

    class FakeMenu:
        SEPARATOR = object()

        def __init__(self, *items):
            self.items = items

    class FakeMenuItem:
        def __init__(self, text, action, enabled=True, default=False):
            self.text = text
            self.action = action
            self.enabled = enabled
            self.default = default

    class FakeIcon:
        def __init__(self, name, image, title, menu=None):
            created["name"] = name
            created["title"] = title
            created["menu"] = menu
            self.visible = False

    fake_pystray = types.ModuleType("pystray")
    fake_pystray.Icon = FakeIcon
    fake_pystray.Menu = FakeMenu
    fake_pystray.MenuItem = FakeMenuItem
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)

    icon = _tray_icon(WatchLoop(_args()))
    assert icon is not None
    assert icon.visible is True
    assert created["name"] == "SystemInfoReporter"
    assert created["title"] == PRODUCT_NAME
    labels = [getattr(item, "text", None) for item in created["menu"].items]
    assert f"{PRODUCT_NAME} — online" in labels
    assert "Exit" in labels
    update_item = next(
        item for item in created["menu"].items
        if getattr(item, "text", None) == "Check for updates…"
    )
    assert update_item.default is True


def test_watch_product_name_survives_missing_version_attr():
    import system_info.watch as watch

    assert watch.PRODUCT_NAME == "System Info Reporter"
    from system_info.version import PRODUCT_NAME
    from system_info.watch import _show_tray

    seen = {}

    class FakeIcon:
        visible = False

        def notify(self, message, title):
            seen["message"] = message
            seen["title"] = title

    icon = FakeIcon()
    _show_tray(icon)
    assert icon.visible is True
    assert seen["title"] == PRODUCT_NAME
    assert "system tray" in seen["message"].lower()


def test_handle_restart_failure_reports_false(monkeypatch):
    import subprocess

    def boom(*a, **k):
        raise OSError("no")

    monkeypatch.setattr(subprocess, "Popen", boom)
    loop = WatchLoop(_args())
    assert loop.handle_restart() is False


def test_full_report_stops_when_update_staged(monkeypatch):
    loop = WatchLoop(_args())
    monkeypatch.setattr("system_info.cli.collect_all", lambda args: {})
    monkeypatch.setattr("system_info.cli.save_report", lambda *a, **k: None)
    monkeypatch.setattr("system_info.update.maybe_auto_update", lambda quiet=True: True)
    stopped = []
    monkeypatch.setattr(loop, "_stop_for_update", lambda: stopped.append(True))
    loop.full_report()
    assert stopped == [True]


def test_full_report_leaves_watcher_running_when_no_update(monkeypatch):
    loop = WatchLoop(_args())
    monkeypatch.setattr("system_info.cli.collect_all", lambda args: {})
    monkeypatch.setattr("system_info.cli.save_report", lambda *a, **k: None)
    monkeypatch.setattr("system_info.update.maybe_auto_update", lambda quiet=True: False)
    stopped = []
    monkeypatch.setattr(loop, "_stop_for_update", lambda: stopped.append(True))
    loop.full_report()
    assert stopped == []


def test_run_tray_or_wait_sets_stop_when_run_returns(monkeypatch):
    from system_info.watch import WatchLoop, _run_tray_or_wait, _show_tray

    seen = {}

    class Tray:
        visible = False

        def run(self, setup=None):
            seen["setup"] = setup
            if setup:
                setup(self)

    loop = WatchLoop(_args())
    _run_tray_or_wait(loop, Tray())
    assert seen["setup"] is _show_tray
    assert loop._stop.is_set()


def test_run_tray_or_wait_falls_back_when_setup_unsupported():
    from system_info.watch import WatchLoop, _run_tray_or_wait

    class Tray:
        visible = False

        def run(self):
            self.visible = True

    loop = WatchLoop(_args())
    _run_tray_or_wait(loop, Tray())
    assert loop._stop.is_set()


def test_run_tray_or_wait_keeps_running_when_tray_raises(monkeypatch, tmp_path):
    from system_info.watch import WatchLoop, _run_tray_or_wait

    waited = []

    class Tray:
        def run(self, setup=None):
            raise RuntimeError("win32 notify icon failed")

    loop = WatchLoop(_args())
    monkeypatch.setattr(loop._stop, "wait", lambda: waited.append(True))
    monkeypatch.setattr(
        "system_info.win_runtime.crash_log_path", lambda: tmp_path / "crash.log"
    )
    monkeypatch.setattr("system_info.win_runtime.user_config_dir", lambda: tmp_path)
    _run_tray_or_wait(loop, Tray())
    assert waited == [True]
    assert not loop._stop.is_set()
    assert (tmp_path / "crash.log").is_file()


def test_run_tray_or_wait_without_icon_waits(monkeypatch, tmp_path):
    from system_info.watch import WatchLoop, _run_tray_or_wait

    waited = []
    loop = WatchLoop(_args())
    monkeypatch.setattr(loop._stop, "wait", lambda: waited.append(True))
    monkeypatch.setattr("system_info.win_runtime.user_config_dir", lambda: tmp_path)
    _run_tray_or_wait(loop, None)
    assert waited == [True]
    assert not loop._stop.is_set()