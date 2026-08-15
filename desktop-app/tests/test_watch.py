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
    assert HEARTBEAT_INTERVAL <= 300
    assert HOUR_INTERVAL == 3600


@pytest.mark.parametrize(
    "manifest, staged, expected_fragment",
    [
        (None, None, "Already up to date"),
        ({"version": "9.9.9"}, "/x/apply-update.cmd", "staged"),
        ({"version": "9.9.9"}, None, "could not be applied"),
    ],
)
def test_handle_update_request(monkeypatch, manifest, staged, expected_fragment):
    import system_info.update as update_mod

    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: manifest)
    monkeypatch.setattr(update_mod, "apply_windows_update", lambda *a, **k: staged)

    loop = WatchLoop(_args())
    message, title = loop.handle_update_request()

    assert expected_fragment in message
    if not manifest:
        assert "no update" in title
    elif staged:
        assert "restart the app to apply" in message.lower()
        assert "update ready" in title


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


def test_handle_restart_failure_reports_false(monkeypatch):
    import subprocess

    def boom(*a, **k):
        raise OSError("no")

    monkeypatch.setattr(subprocess, "Popen", boom)
    loop = WatchLoop(_args())
    assert loop.handle_restart() is False