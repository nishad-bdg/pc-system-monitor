import argparse

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