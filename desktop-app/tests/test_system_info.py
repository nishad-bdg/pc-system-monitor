import argparse
import json

import pytest

from system_info.geo import Location, geo_locate
from system_info.ip import get_private_ip, get_public_ip, get_mac_address, get_mac_addresses
from system_info.os_info import OSInfo, collect_os_info
from system_info.resources import SystemResources, collect_resources
from system_info.disk import collect_disk_info, _base_device, _is_real_device, DiskDevice, DiskPartition
from system_info import cli


class FakeResponse:
    def __init__(self, text="", payload=None):
        self._text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    @property
    def text(self):
        return self._text


def test_send_heartbeat_success(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=5):
        sent["url"] = url
        sent["payload"] = json
        return FakeResponse(payload={"status": "ok"})

    monkeypatch.setattr(cli.requests, "post", fake_post)
    result = cli.send_heartbeat({"device_id": "d1", "pc_name": "PC"}, "http://x", "sk-key")
    assert result == {"status": "ok"}
    assert sent["url"] == "http://x/heartbeat"
    assert sent["payload"] == {"device_id": "d1", "pc_name": "PC"}


def test_send_heartbeat_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(cli.requests, "post", boom)
    assert cli.send_heartbeat({"device_id": "d1"}, "http://x", "sk-key") is None


def test_geo_locate_happy_path(monkeypatch):
    payload = {
        "status": "success",
        "query": "8.8.8.8",
        "city": "Mountain View",
        "regionName": "California",
        "country": "United States",
        "countryCode": "US",
        "lat": 37.4056,
        "lon": -122.0775,
        "isp": "Google LLC",
        "timezone": "America/Los_Angeles",
    }
    monkeypatch.setattr("system_info.geo.requests.get", lambda *a, **k: FakeResponse(payload=payload))
    loc = geo_locate("8.8.8.8")
    assert isinstance(loc, Location)
    assert loc.city == "Mountain View"
    assert loc.isp == "Google LLC"
    assert loc.lat == 37.4056


def test_geo_locate_failure_returns_none(monkeypatch):
    monkeypatch.setattr("system_info.geo.requests.get", lambda *a, **k: FakeResponse(payload={"status": "fail"}))
    assert geo_locate("8.8.8.8") is None


def test_geo_locate_request_exception_returns_none(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr("system_info.geo.requests.get", boom)
    assert geo_locate("8.8.8.8") is None


def test_get_public_ip(monkeypatch):
    monkeypatch.setattr("system_info.ip.requests.get", lambda *a, **k: FakeResponse(text="1.2.3.4"))
    assert get_public_ip() == "1.2.3.4"


def test_get_public_ip_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr("system_info.ip.requests.get", boom)
    assert get_public_ip() is None


def test_get_private_ip(monkeypatch):
    ip = get_private_ip()
    assert isinstance(ip, str) and ip


def test_get_mac_addresses(monkeypatch):
    from collections import namedtuple

    Snic = namedtuple("Snic", "family address netmask broadcast ptp")
    addrs = {
        "en0": [Snic(2, "10.0.0.1", None, None, None), Snic(17, "aa:bb:cc:dd:ee:ff", None, None, None)],
        "lo0": [Snic(17, "00:00:00:00:00:00", None, None, None)],
        "Wi-Fi": [Snic(17, "11:22:33:44:55:66", None, None, None)],
        "Ethernet": [Snic(17, "12:23:34:45:56:67", None, None, None)],
    }
    monkeypatch.setattr("system_info.ip.psutil.net_if_addrs", lambda: addrs)
    monkeypatch.setattr("system_info.ip.psutil.AF_LINK", 17)

    macs = get_mac_addresses()
    assert macs == [
        {"interface": "Ethernet", "mac": "12:23:34:45:56:67"},
        {"interface": "Wi-Fi", "mac": "11:22:33:44:55:66"},
        {"interface": "en0", "mac": "aa:bb:cc:dd:ee:ff"},
    ]
    # all-zero skipped; de-duplicated across identical interface MACs


def test_format_mac(monkeypatch):
    from system_info.ip import _format_mac
    assert _format_mac(0x112233445566) == "11:22:33:44:55:66"


def test_collect_os_info_fields():
    info = collect_os_info()
    assert isinstance(info, OSInfo)
    assert info.system in ("Darwin", "Windows", "Linux")
    for field in ("system", "release", "machine", "processor", "python_version", "hostname"):
        assert getattr(info, field)


def test_location_to_dict():
    loc = Location(ip="1.2.3.4", city="Paris", region=None, country="France",
                   country_code="FR", lat=48.85, lon=2.35, isp="X", timezone="Europe/Paris")
    d = loc.to_dict()
    assert d["city"] == "Paris"
    assert set(d) == {"ip", "city", "region", "country", "country_code", "lat", "lon", "isp", "timezone"}


def test_collect_resources_fields():
    r = collect_resources()
    assert isinstance(r, SystemResources)
    assert r.cpu_count >= 1
    assert r.ram_total > 0
    assert 0 <= r.ram_percent <= 100
    assert 0 <= r.cpu_percent <= 100


def test_resources_to_dict_keys():
    loc = SystemResources(cpu_count=8, cpu_count_physical=4, cpu_percent=10.0, cpu_freq_mhz=1000.0,
                          ram_total=1024, ram_used=512, ram_available=512, ram_free=256,
                          ram_percent=50.0, swap_total=2048, swap_used=0, swap_percent=0.0, battery=None,
                          ram_speed_mhz=None, ram_type=None, cpu_brand=None)
    assert set(loc.to_dict()) == {
            "cpu_count", "cpu_count_physical", "cpu_percent", "cpu_freq_mhz",
            "cpu_brand",
            "ram_total", "ram_used", "ram_available", "ram_free", "ram_percent",
            "swap_total", "swap_used", "swap_percent", "battery",
            "ram_speed_mhz", "ram_type",
        }


def test_collect_battery_status_charging(monkeypatch):
    import psutil
    from system_info.resources import _collect_battery

    class FakeBatt:
        percent = 45.0
        power_plugged = True
        secsleft = 3600

    monkeypatch.setattr("system_info.resources.psutil.sensors_battery", lambda: FakeBatt())
    batt = _collect_battery()
    assert batt is not None
    assert batt["status"] == "charging"
    assert batt["power_plugged"] is True
    assert batt["seconds_left"] == 3600


def test_collect_battery_status_full(monkeypatch):
    from system_info.resources import _collect_battery

    class FakeBatt:
        percent = 100.0
        power_plugged = True
        secsleft = -1

    monkeypatch.setattr("system_info.resources.psutil.sensors_battery", lambda: FakeBatt())
    batt = _collect_battery()
    assert batt is not None
    assert batt["status"] == "full"
    assert batt["seconds_left"] is None


def test_collect_battery_status_discharging(monkeypatch):
    from system_info.resources import _collect_battery

    class FakeBatt:
        percent = 30.0
        power_plugged = False
        secsleft = 5400

    monkeypatch.setattr("system_info.resources.psutil.sensors_battery", lambda: FakeBatt())
    batt = _collect_battery()
    assert batt is not None
    assert batt["status"] == "discharging"
    assert batt["power_plugged"] is False
    assert batt["seconds_left"] == 5400


def test_collect_battery_none_on_desktop(monkeypatch):
    from system_info.resources import _collect_battery

    monkeypatch.setattr("system_info.resources.psutil.sensors_battery", lambda: None)
    assert _collect_battery() is None


def test_fmt_bytes():
    assert cli._fmt_bytes(1024) == "1.00 KiB"
    assert cli._fmt_bytes(1024 * 1024) == "1.00 MiB"
    assert cli._fmt_bytes(1536) == "1.50 KiB"


def test_classify_connection():
    from system_info.printers import classify_connection

    assert classify_connection("usb://HP/DeskJet") == "usb"
    assert classify_connection("USB001") == "usb"
    assert classify_connection("ipp://192.168.1.20/ipp/print") == "network"
    assert classify_connection("IP_192.168.1.50") == "network"
    assert classify_connection("WSD-abc") == "network"
    assert classify_connection("192.168.0.10:9100") == "network"
    assert classify_connection("Fax") == "other"
    assert classify_connection("") == "other"


def test_extract_printer_ip():
    from system_info.printers import extract_printer_ip

    assert extract_printer_ip("ipp://192.168.1.20/ipp/print", "network") == "192.168.1.20"
    assert extract_printer_ip("IP_10.0.0.5", "network") == "10.0.0.5"
    assert extract_printer_ip("socket://printer.local:9100", "network") is None
    assert extract_printer_ip("usb://HP/DeskJet", "usb") is None


def test_parse_env_file(tmp_path):
    from system_info.config import parse_env_file

    path = tmp_path / "config.env"
    path.write_text(
        "SYSTEM_INFO_API_URL=https://api.example\n"
        "SYSTEM_INFO_API_KEY=sk-test\n"
        "# comment\n"
        "SYSTEM_INFO_PC_NAME=Office-1\n",
        encoding="utf-8",
    )
    values = parse_env_file(path)
    assert values["SYSTEM_INFO_API_URL"] == "https://api.example"
    assert values["SYSTEM_INFO_API_KEY"] == "sk-test"
    assert values["SYSTEM_INFO_PC_NAME"] == "Office-1"


def test_is_newer_version():
    from system_info.update import is_newer

    assert is_newer("0.2.0", "0.1.0")
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("0.1.0", "0.2.0")
    assert is_newer("v1.0.0", "0.9.9")


def test_maybe_auto_update_restarts_into_watch(monkeypatch):
    from system_info.update import maybe_auto_update

    called = {}

    def fake_restart(manifest):
        called["manifest"] = manifest
        return "/x/apply-update-restart.cmd"

    monkeypatch.setattr("system_info.update.check_for_update", lambda: {"version": "9.9.9"})
    monkeypatch.setattr("system_info.update.apply_update_and_restart", fake_restart)
    monkeypatch.setattr("system_info.update.apply_windows_update", lambda m: (_ for _ in ()).throw(AssertionError("must restart, not stage-only")))
    assert maybe_auto_update() is True
    assert called["manifest"]["version"] == "9.9.9"


def test_apply_update_and_restart_script_relaunches_tray(monkeypatch, tmp_path):
    import subprocess
    from pathlib import Path

    from system_info import update as update_mod

    pending = tmp_path / "system-info.new.exe"
    pending.write_bytes(b"new")
    exe = tmp_path / "system-info.exe"
    monkeypatch.setattr(update_mod, "is_frozen", lambda: True)
    monkeypatch.setattr("system_info.update.os.name", "nt")
    monkeypatch.setattr(update_mod, "_download_new_exe", lambda manifest: pending)
    monkeypatch.setattr(update_mod, "install_dir", lambda: tmp_path)
    monkeypatch.setattr(update_mod.sys, "executable", str(exe))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: object())

    path = update_mod.apply_update_and_restart({"version": "9.9.9"})
    assert path
    script = Path(path).read_text(encoding="utf-8")
    assert "--watch" in script
    assert "start" in script.lower()
    assert str(exe) in script


def test_collect_network_usage(monkeypatch):
    from system_info import network

    class Counters:
        def __init__(self, sent, recv):
            self.bytes_sent = sent
            self.bytes_recv = recv

    # first read, 6 window samples, then a final read
    values = iter([
        Counters(1000, 2000),  # initial
        Counters(1500, 2500),  # +500 / +500
        Counters(1600, 3000),  # +100 / +500
        Counters(1800, 5000),  # +200 / +2000  <- peak recv burst
        Counters(2000, 5200),  # +200 / +200
        Counters(2200, 5400),  # +200 / +200
        Counters(2400, 5600),  # +200 / +200
        Counters(2500, 5900),  # final
    ])
    monkeypatch.setattr(network.psutil, "net_io_counters", lambda: next(values))
    monkeypatch.setattr(network.time, "sleep", lambda s: None)
    usage = network.collect_network_usage(interval=0.5)
    assert usage.bytes_sent == 2500
    assert usage.bytes_recv == 5900
    assert usage.send_rate_bps == 1000.0  # peak 500 bytes / 0.5s
    assert usage.recv_rate_bps == 4000.0  # peak 2000 bytes / 0.5s burst

def test_split_seconds_by_utc_day():
    from system_info.uptime import split_seconds_by_utc_day

    # 2026-08-11 23:00 UTC → 2026-08-12 01:00 UTC = 2 hours
    start = 1786492800.0  # will compute from known midnights
    # Use datetime-derived stamps for clarity
    from datetime import datetime, timezone

    start = datetime(2026, 8, 11, 23, 0, tzinfo=timezone.utc).timestamp()
    end = datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc).timestamp()
    buckets = split_seconds_by_utc_day(start, end)
    assert buckets["2026-08-11"] == 3600.0
    assert buckets["2026-08-12"] == 3600.0


def test_uptime_reboot_skips_offline(tmp_path):
    from system_info.uptime import collect_uptime, save_state
    from datetime import datetime, timezone

    path = tmp_path / "uptime.json"
    t0 = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc).timestamp()
    boot1 = t0 - 3600
    # First session ends at t0
    save_state(path, boot_time=boot1, seen_at=t0, by_day={"2026-08-12": 3600.0})

    # Offline 2h, reboot at t0+7200, run at t0+7800 (1h after boot)
    boot2 = t0 + 7200
    now = boot2 + 3600
    info = collect_uptime(now=now, boot_time=boot2, state_path=path)
    # Should add only 3600 for new session, not the offline gap
    assert info.by_day["2026-08-12"] == 7200.0
    assert info.uptime_seconds == 3600.0
    assert info.day_timezone == "UTC"


def test_uptime_same_boot_credits_gap(tmp_path):
    from system_info.uptime import collect_uptime, save_state
    from datetime import datetime, timezone

    path = tmp_path / "uptime.json"
    boot = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc).timestamp()
    seen = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc).timestamp()
    save_state(path, boot_time=boot, seen_at=seen, by_day={"2026-08-12": 3600.0})
    now = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc).timestamp()
    info = collect_uptime(now=now, boot_time=boot, state_path=path)
    assert info.by_day["2026-08-12"] == 7200.0


def test_macos_print_count_parses_ipp_report(monkeypatch):
    """ipptool needs a real temp file (stdin '-' is rejected) and the count
    is parsed from the PASS/attribute report."""
    from system_info import printers
    import subprocess as _sp

    captured: dict = {}

    def fake_run(cmd, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        assert "/tmp/" in cmd[-1] or ".ipp" in cmd[-1], f"no temp file: {cmd}"
        assert cmd[0] == "ipptool"
        assert cmd[1] == "-t"
        assert not cmd[-1].startswith("ipp://"), "URI must come before file path"
        return _sp.CompletedProcess(cmd, 0, stdout="printer-impressions-completed (integer) = 4821\n", stderr="")

    monkeypatch.setattr(printers.subprocess, "run", fake_run)
    result = printers._macos_print_count("Office_Laser")
    assert result == 4821


def test_macos_print_count_no_match_returns_none(monkeypatch):
    from system_info import printers
    import subprocess as _sp

    def fake_run(cmd, capture_output, text, timeout, check):
        return _sp.CompletedProcess(cmd, 0, stdout="something else\n", stderr="")

    monkeypatch.setattr(printers.subprocess, "run", fake_run)
    assert printers._macos_print_count("Office_Laser") is None


def test_collect_printers_macos(monkeypatch):
    from system_info import printers

    monkeypatch.setattr(printers.os, "name", "posix")
    monkeypatch.setattr(printers, "_macos_print_count", lambda name: 42 if name == "Office_Laser" else None)
    monkeypatch.setattr(
        printers,
        "_run",
        lambda cmd, timeout=8.0: (
            "device for Office_Laser: ipp://192.168.1.20/ipp/print\n"
            "device for DeskJet: usb://HP/DeskJet%20Ink\n"
            "device for OneNote: nul:\n"
        ),
    )
    info = printers.collect_printers()
    assert info.count == 3
    assert [p.name for p in info.usb] == ["DeskJet"]
    assert info.network[0].name == "Office_Laser"
    assert info.network[0].ip == "192.168.1.20"
    assert info.network[0].print_count == 42
    assert [p.name for p in info.other] == ["OneNote"]
    payload = info.to_dict()
    assert payload["count"] == 3
    assert payload["usb"][0]["port"].startswith("usb://")
    assert "ip" in payload["network"][0]
    assert "print_count" in payload["network"][0]


def test_collect_printers_windows(monkeypatch):
    from system_info import printers

    monkeypatch.setattr(printers.os, "name", "nt")
    payload = json.dumps(
        [
            {"Name": "HP USB", "PortName": "USB001"},
            {"Name": "Floor Printer", "PortName": "IP_10.0.0.5"},
            {"Name": "Microsoft Print to PDF", "PortName": "PORTPROMPT:"},
        ]
    )
    monkeypatch.setattr(printers, "_run", lambda cmd, timeout=8.0: payload)
    monkeypatch.setattr(printers, "_windows_print_counts", lambda: {"Floor Printer": 100})
    info = printers.collect_printers()
    assert info.count == 3
    assert [p.name for p in info.usb] == ["HP USB"]
    assert info.network[0].ip == "10.0.0.5"
    assert info.network[0].print_count == 100
    assert [p.name for p in info.other] == ["Microsoft Print to PDF"]

def test_resolve_pc_name_macos_ignores_explicit(monkeypatch):
    from system_info import device

    monkeypatch.setattr(device.os, "name", "posix")
    monkeypatch.setattr(device, "get_device_name", lambda: "MacBook-Pro")
    assert device.resolve_pc_name("Office-PC-3") == "MacBook-Pro"
    assert device.resolve_pc_name("") == "MacBook-Pro"
    assert device.resolve_pc_name(None) == "MacBook-Pro"


def test_resolve_pc_name_windows_prefers_explicit(monkeypatch):
    from system_info import device

    monkeypatch.setattr(device.os, "name", "nt")
    monkeypatch.setattr(device, "get_device_name", lambda: "DESKTOP-ABC")
    assert device.resolve_pc_name("Office-PC-3") == "Office-PC-3"
    assert device.resolve_pc_name("  Lab-Win-01  ") == "Lab-Win-01"
    assert device.resolve_pc_name("") == "DESKTOP-ABC"
    assert device.resolve_pc_name(None) == "DESKTOP-ABC"


def test_run_show_sys_only(monkeypatch):
    monkeypatch.setattr(cli, "geo_locate", lambda ip: None)
    monkeypatch.setattr(cli, "collect_os_info", lambda: OSInfo(
        system="Darwin", release="25", version="", machine="arm64", processor="arm",
        architecture="64bit", python_version="3.14", hostname="h",
        platform_detail="macOS"))
    monkeypatch.setattr(cli, "get_private_ip", lambda: "192.168.1.5")
    monkeypatch.setattr(cli, "get_public_ip", lambda: None)
    monkeypatch.setattr(cli, "collect_resources", lambda: SystemResources(
        cpu_count=8, cpu_count_physical=4, cpu_percent=10.0, cpu_freq_mhz=1000.0,
        ram_total=1024, ram_used=512, ram_available=512, ram_free=256, ram_percent=50.0,
        swap_total=2048, swap_used=0, swap_percent=0.0, battery=None, ram_speed_mhz=None, ram_type=None,
        cpu_brand=None))
    monkeypatch.setattr(
        cli,
        "collect_uptime",
        lambda: type("U", (), {"to_dict": lambda self: {
            "boot_time": 1.0,
            "uptime_seconds": 120.0,
            "by_day": {"2026-08-12": 120.0},
            "day_timezone": "UTC",
        }})(),
    )
    monkeypatch.setattr(cli, "resolve_pc_name", lambda explicit=None: "MacBook-Pro")
    monkeypatch.setattr(cli, "get_or_create_device_id", lambda pc_name=None: "device-1")
    monkeypatch.setattr(cli, "save_report", lambda data, url, api_key="": None)

    args = cli.build_parser().parse_args(["--sys", "--json"])
    data = _capture_json(monkeypatch, args)
    assert "resources" in data
    assert data["uptime"]["uptime_seconds"] == 120.0
    assert "os" not in data
    assert "private_ip" not in data
    assert data["location"] is None
    assert data["pc_name"] == "MacBook-Pro"
    assert data["device_id"] == "device-1"


def test_default_to_watch_frozen_windows_with_no_flags(monkeypatch):
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr("system_info.config.is_frozen", lambda: True)
    args = cli.build_parser().parse_args([])
    assert cli._default_to_watch(args) is True


def test_default_to_watch_skips_one_shot_and_non_frozen(monkeypatch):
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr("system_info.config.is_frozen", lambda: True)
    assert cli._default_to_watch(cli.build_parser().parse_args(["--sys"])) is False
    assert cli._default_to_watch(cli.build_parser().parse_args(["--heartbeat"])) is False
    assert cli._default_to_watch(cli.build_parser().parse_args(["--watch"])) is False

    monkeypatch.setattr("system_info.config.is_frozen", lambda: False)
    assert cli._default_to_watch(cli.build_parser().parse_args([])) is False


def test_frozen_windows_run_starts_watch(monkeypatch):
    called = {}
    def fake_watch(args):
        called["watch"] = True
        return 0

    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr("system_info.config.is_frozen", lambda: True)
    monkeypatch.setattr(cli, "register_startup", lambda: True)
    monkeypatch.setattr("system_info.watch.run_watch", fake_watch)

    args = cli.build_parser().parse_args([])
    assert cli.run(args) == 0
    assert called.get("watch") is True


def _capture_json(monkeypatch, args):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.run(args)
    import json
    return json.loads(buf.getvalue())


def test_base_device():
    assert _base_device("C:\\") == "C:"
    assert _base_device("D:/") == "D:"
    assert _base_device("/dev/disk3s1s1") == "/dev/disk3"
    assert _base_device("/dev/sda1") == "/dev/sda"
    assert _base_device("/dev/nvme0n1p1") == "/dev/nvme0n1"


def test_is_real_device():
    assert _is_real_device("/dev/disk3s1")
    assert _is_real_device("C:\\")
    assert not _is_real_device("devfs")
    assert not _is_real_device("//server/share")


def test_collect_disk_info(monkeypatch):
    from collections import namedtuple

    Part = namedtuple("Part", "device mountpoint fstype opts")
    Usage = namedtuple("Usage", "total used free percent")

    parts = [
        Part("/dev/disk3s1s1", "/", "apfs", "rw"),
        Part("/dev/disk3s1s5", "/System/Volumes/Data", "apfs", "rw"),
        Part("/dev/disk4s1", "/Volumes/Ext", "apfs", "rw"),
        Part("devfs", "/dev", "devfs", ""),
        Part("//server/share", "/Volumes/share", "smbfs", ""),
    ]
    usages = {
        "/": Usage(100, 60, 40, 60.0),
        "/System/Volumes/Data": Usage(200, 100, 100, 50.0),
        "/Volumes/Ext": Usage(50, 25, 25, 50.0),
    }
    monkeypatch.setattr("system_info.disk.psutil.disk_partitions", lambda all=True: parts)
    monkeypatch.setattr("system_info.disk.psutil.disk_usage", lambda mp: usages[mp])

    info = collect_disk_info()
    assert [d.device for d in info.devices] == ["/dev/disk3", "/dev/disk4"]
    devices = {d.device: d for d in info.devices}
    assert devices["/dev/disk3"].total == 300
    assert devices["/dev/disk3"].used == 160
    assert devices["/dev/disk3"].free == 140
    assert len(info.partitions) == 3  # virtual/network mounts excluded


def test_collect_disk_info_shared_container(monkeypatch):
    from collections import namedtuple

    Part = namedtuple("Part", "device mountpoint fstype opts")
    Usage = namedtuple("Usage", "total used free percent")

    parts = [
        Part("/dev/disk3s1", "/System/Volumes/Data", "apfs", "rw"),
        Part("/dev/disk3s2", "/System/Volumes/VM", "apfs", "rw"),
    ]
    usages = {
        "/System/Volumes/Data": Usage(500, 200, 300, 40.0),
        "/System/Volumes/VM": Usage(500, 100, 300, 20.0),
    }
    monkeypatch.setattr("system_info.disk.psutil.disk_partitions", lambda all=True: parts)
    monkeypatch.setattr("system_info.disk.psutil.disk_usage", lambda mp: usages[mp])

    info = collect_disk_info()
    d = info.devices[0]
    assert d.device == "/dev/disk3"
    assert d.total == 500  # shared container, not 1000
    assert d.free == 300
    assert d.used == 200


def test_disk_to_dict():
    d = DiskDevice("/dev/disk0", 100, 50, 50, 50.0)
    p = DiskPartition("/dev/disk0s1", "/", "apfs", 100, 50, 50, 50.0)
    assert d.to_dict()["device"] == "/dev/disk0"
    assert set(p.to_dict()) == {"device", "mountpoint", "fstype", "total", "used", "free", "percent"}


def test_security_collect_windows(monkeypatch):
    from system_info.security import collect_security_info, SecurityInfo

    monkeypatch.setattr("system_info.security.os.name", "nt")
    monkeypatch.setattr(
        "system_info.security._collect_windows",
        lambda: [
            {"name": "Windows Defender", "vendor": "Windows Defender", "active": True}
        ],
    )
    info = collect_security_info()
    assert info.platform == "windows"
    assert info.count == 1
    assert info.installed[0]["name"] == "Windows Defender"


def test_security_product_state_active():
    from system_info.security import _product_state_active

    assert _product_state_active(0x1000) is True
    assert _product_state_active(0x0000) is False
    assert _product_state_active(None) is None


def test_security_match_vendor():
    from system_info.security import _match_vendor

    assert _match_vendor("Norton Internet Security") == "Norton"
    assert _match_vendor("McAfee Total Protection") == "McAfee"
    assert _match_vendor("Some Random App") is None


def test_security_macos_defaults_to_xprotect(monkeypatch):
    from system_info.security import collect_security_info

    monkeypatch.setattr("system_info.security.os.name", "posix")
    monkeypatch.setattr("system_info.security._scan_installed_paths", lambda: [])
    monkeypatch.setattr("system_info.security._scan_processes", lambda: [])
    monkeypatch.setattr("system_info.security._scan_launch_items", lambda: [])
    info = collect_security_info()
    assert info.platform == "macos"
    assert any("XProtect" in p.name for p in info.installed)


def test_security_macos_finds_known_app(monkeypatch):
    from system_info.security import collect_security_info

    monkeypatch.setattr("system_info.security.os.name", "posix")
    monkeypatch.setattr(
        "system_info.security._scan_installed_paths", lambda: ["Sophos Endpoint.app"]
    )
    monkeypatch.setattr("system_info.security._scan_processes", lambda: [])
    monkeypatch.setattr("system_info.security._scan_launch_items", lambda: [])
    info = collect_security_info()
    assert any("sophos" in p.name.lower() for p in info.installed)


def test_security_windows_fallback_when_security_center_empty(monkeypatch):
    from system_info.security import collect_security_info

    monkeypatch.setattr("system_info.security.os.name", "nt")
    monkeypatch.setattr("system_info.security._collect_windows_security_center", lambda: [])
    monkeypatch.setattr(
        "system_info.security._scan_installed_paths",
        lambda: ["C:\\Program Files\\Norton Security\\Norton.exe"],
    )
    monkeypatch.setattr("system_info.security._scan_processes", lambda: [])
    monkeypatch.setattr("system_info.security._scan_launch_items", lambda: [])
    monkeypatch.setattr("system_info.security._collect_windows_expiry_hints", lambda: {})
    info = collect_security_info()
    assert info.platform == "windows"
    assert any(p.vendor == "Norton" for p in info.installed)


def test_security_product_to_dict_includes_expiry():
    from datetime import date, timedelta

    from system_info.security import SecurityProduct, _apply_expiry

    future = date(2030, 3, 15)
    product = _apply_expiry(
        SecurityProduct(name="ESET NOD32", vendor="ESET", active=True),
        future,
        today=date(2030, 1, 14),
    )
    payload = product.to_dict()
    assert payload["expiry_date"] == "2030-03-15"
    assert payload["expired"] is False
    assert payload["days_remaining"] == 60


def test_expiry_status_expired():
    from datetime import date

    from system_info.security import SecurityProduct, _apply_expiry

    product = _apply_expiry(
        SecurityProduct(name="Norton", vendor="Norton"),
        date(2026, 1, 1),
        today=date(2026, 8, 15),
    )
    assert product.expired is True
    assert product.days_remaining == 0
    assert product.expiry_date == "2026-01-01"


def test_parse_expiry_date_formats():
    from datetime import date

    from system_info.security import _parse_expiry_date

    assert _parse_expiry_date("2030-12-31") == date(2030, 12, 31)
    assert _parse_expiry_date("2018-11-17T12:00:00Z") == date(2018, 11, 17)
    assert _parse_expiry_date("17/11/2018") == date(2018, 11, 17)
    assert _parse_expiry_date(1893456000) == date(2030, 1, 1)  # unix
    assert _parse_expiry_date("not-a-date") is None
    assert _parse_expiry_date(None) is None


def test_interpret_registry_days_remaining():
    from datetime import date

    from system_info.security import _interpret_registry_expiry

    expiry = _interpret_registry_expiry("LicDaysTillExpiration", 12, today=date(2026, 8, 15))
    assert expiry == date(2026, 8, 27)
    expiry = _interpret_registry_expiry("SurveyDataInfo", '{"days_left": 3}', today=date(2026, 8, 15))
    assert expiry == date(2026, 8, 18)


def test_eset_license_xml_expiration():
    from datetime import date

    from system_info.security import _eset_expiry_from_license

    xml = (
        "<ESET><PRODUCT_LICENSE_FILE><LICENSE><ACTIVE_PRODUCT "
        'EXPIRATION_DATE="2027-04-01T12:00:00Z"/></LICENSE>'
        "</PRODUCT_LICENSE_FILE></ESET>"
    )
    assert _eset_expiry_from_license(xml) == date(2027, 4, 1)


def test_attach_windows_expiry_matches_vendor(monkeypatch):
    from datetime import date

    from system_info.security import SecurityProduct, _attach_windows_expiry

    monkeypatch.setattr("system_info.security.os.name", "nt")
    monkeypatch.setattr(
        "system_info.security._collect_windows_expiry_hints",
        lambda: {"ESET": date(2026, 9, 14)},
    )
    products = [
        SecurityProduct(name="ESET NOD32 Antivirus", vendor="ESET", active=True),
        SecurityProduct(name="Windows Defender", vendor="Windows Defender", active=True),
    ]
    _attach_windows_expiry(products, today=date(2026, 8, 15))
    assert products[0].expired is False
    assert products[0].days_remaining == 30
    assert products[0].expiry_date == "2026-09-14"
    assert products[1].expiry_date is None
    assert products[1].expired is None


def test_health_macos_disk_dedupe(monkeypatch):
    from system_info.health import _collect_macos_disks

    payload = {
        "SPStorageDataType": [
            {
                "bsd_name": "disk3s5",
                "physical_drive": {
                    "device_name": "APPLE SSD AP0256Z",
                    "medium_type": "ssd",
                    "smart_status": "Verified",
                    "is_internal_disk": "yes",
                },
            },
            {
                "bsd_name": "disk3s1s1",
                "physical_drive": {
                    "device_name": "APPLE SSD AP0256Z",
                    "medium_type": "ssd",
                    "smart_status": "Verified",
                    "is_internal_disk": "yes",
                },
            },
        ]
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    disks = _collect_macos_disks()
    assert len(disks) == 1
    assert disks[0].device == "disk3"
    assert disks[0].media_type == "ssd"
    assert disks[0].health == "ok"


def test_health_macos_battery(monkeypatch):
    from system_info.health import _collect_macos_battery

    payload = {
        "SPPowerDataType": [
            {
                "_name": "spbattery_information",
                "sppower_battery_health_info": {
                    "sppower_battery_cycle_count": 471,
                    "sppower_battery_health": "Good",
                    "sppower_battery_health_maximum_capacity": "82%",
                },
            }
        ]
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    batt = _collect_macos_battery()
    assert batt is not None
    assert batt.cycle_count == 471
    assert batt.health_percent == 82
    assert batt.condition == "Good"


def test_health_media_type():
    from system_info.health import _to_media_type, _derive_health

    assert _to_media_type("ssd") == "ssd"
    assert _to_media_type("HDD") == "hdd"
    assert _to_media_type("") == "unknown"
    assert _derive_health("Verified") == "ok"
    assert _derive_health("Failing") == "fail"
    assert _derive_health("Not Supported") == "unknown"


def test_health_windows_battery_health_percent(monkeypatch):
    from system_info.health import _collect_windows_battery

    payload = {
        "FullChargedCapacity": 5100,
        "DesignedCapacity": 6500,
        "CycleCount": 124,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.health_percent == 78
    assert batt.max_capacity_percent == 78
    assert batt.cycle_count == 124
    assert batt.condition == "Warning"


def test_health_windows_battery_sentinel_values(monkeypatch):
    """ACPI returns (uint32)-1 (4294967295) when capacity is unknown; it must be
    treated as missing rather than producing a bogus health %."""
    from system_info.health import _collect_windows_battery

    payload = {
        "FullChargedCapacity": 4294967295,
        "DesignedCapacity": 4294967295,
        "CycleCount": 4294967295,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is None


def test_health_windows_battery_no_battery_returns_none(monkeypatch):
    from system_info.health import _collect_windows_battery

    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(
            {"FullChargedCapacity": None, "DesignedCapacity": None, "CycleCount": None}
        ),
    )
    assert _collect_windows_battery() is None


def test_health_windows_battery_cycle_only(monkeypatch):
    """Even without capacities, a present cycle count yields a battery doc."""
    from system_info.health import _collect_windows_battery

    payload = {
        "FullChargedCapacity": None,
        "DesignedCapacity": None,
        "CycleCount": 88,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.cycle_count == 88
    assert batt.health_percent is None
    assert batt.condition is None


def _write_battery_report_xml(tmp_path, battery_node, xmlns=None):
    path = tmp_path / "battery-report.xml"
    ns_attr = f' xmlns="{xmlns}"' if xmlns else ""
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<BatteryReport{ns_attr}>\n"
        "  <Created>2026-08-15T10:00:00</Created>\n"
        "  <Batteries>\n"
        f"{battery_node}\n"
        "  </Batteries>\n"
        "</BatteryReport>\n",
        encoding="utf-8",
    )
    return path


def _battery_xml_node(
    design=None,
    full=None,
    cycle=None,
):
    parts = ["    <Battery>"]
    if design is not None:
        parts.append(f"      <DesignCapacity>{design}</DesignCapacity>")
    if full is not None:
        parts.append(f"      <FullChargeCapacity>{full}</FullChargeCapacity>")
    if cycle is not None:
        parts.append(f"      <CycleCount>{cycle}</CycleCount>")
    parts.append("    </Battery>")
    return "\n".join(parts)


def _windows_disk_payload(bus_type, name="Test Disk"):
    return [
        {
            "FriendlyName": name,
            "DeviceId": "0",
            "MediaType": "SSD",
            "HealthStatus": "Healthy",
            "BusType": bus_type,
            "Manufacturer": "Acme",
            "Size": 512000000000,
        }
    ]


def test_health_windows_powercfg_xml_health_and_cycle(tmp_path):
    """powercfg /batteryreport /xml exposes full/design capacity + cycles
    directly, which is far more reliable than root/WMI on most laptops."""
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path,
        "    <Battery>\n"
        "      <ManufacturerName>LGC</ManufacturerName>\n"
        "      <DesignCapacity>6500</DesignCapacity>\n"
        "      <FullChargeCapacity>5100</FullChargeCapacity>\n"
        "      <CycleCount>124</CycleCount>\n"
        "    </Battery>",
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 78
    assert batt.max_capacity_percent == 78
    assert batt.cycle_count == 124
    assert batt.condition == "Warning"


def test_health_windows_powercfg_xml_negative_cycle_count(tmp_path):
    """powercfg reports cycle count as -1 when the vendor doesn't expose it;
    that must be treated as missing, not as a bogus negative count."""
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path,
        "    <Battery>\n"
        "      <DesignCapacity>6500</DesignCapacity>\n"
        "      <FullChargeCapacity>5577</FullChargeCapacity>\n"
        "      <CycleCount>-1</CycleCount>\n"
        "    </Battery>",
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 86
    assert batt.condition == "Good"
    assert batt.cycle_count is None


def test_health_windows_powercfg_xml_no_battery(tmp_path):
    """A desktop with no battery omits the <Battery> node entirely -> None."""
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(tmp_path, "")
    assert _parse_battery_xml(path) is None


def test_health_windows_powercfg_fallback_to_wmi(monkeypatch, tmp_path):
    """When powercfg fails (non-zero exit), WMI is still tried."""
    from system_info.health import _collect_windows_battery

    import subprocess as sp

    def fake_run(cmd, *, capture_output=False, text=False, timeout=None, check=False):
        return sp.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(
        "system_info.health.subprocess.run",
        fake_run,
    )
    payload = {"FullChargedCapacity": 5100, "DesignedCapacity": 6500, "CycleCount": 124}
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: __import__("json").dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.cycle_count == 124
    assert batt.health_percent == 78


def test_health_windows_powercfg_xml_without_namespace(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=5100, cycle=124)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 78
    assert batt.cycle_count == 124
    assert batt.condition == "Warning"


def test_health_windows_powercfg_xml_with_default_namespace(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path,
        _battery_xml_node(design=6500, full=5100, cycle=124),
        xmlns="http://schemas.microsoft.com/windows/2006/battery/batterySchema",
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 78
    assert batt.cycle_count == 124
    assert batt.condition == "Warning"


def test_health_windows_powercfg_xml_cycle_count_zero(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=6500, cycle=0)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.cycle_count == 0
    assert batt.health_percent == 100
    assert batt.condition == "Good"


def test_health_windows_powercfg_xml_cycle_count_acpi_sentinel(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=5577, cycle=4294967295)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.cycle_count is None
    assert batt.health_percent == 86
    assert batt.condition == "Good"


def test_health_windows_powercfg_xml_missing_capacity(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(tmp_path, _battery_xml_node(cycle=12))
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.cycle_count == 12
    assert batt.health_percent is None
    assert batt.max_capacity_percent is None
    assert batt.condition is None


def test_health_windows_powercfg_xml_unknown_health_condition_none(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(tmp_path, _battery_xml_node(cycle=0))
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.cycle_count == 0
    assert batt.health_percent is None
    assert batt.condition is None


def test_health_windows_powercfg_xml_condition_good(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=5200, cycle=10)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 80
    assert batt.condition == "Good"


def test_health_windows_powercfg_xml_condition_warning(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=3900, cycle=200)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 60
    assert batt.condition == "Warning"


def test_health_windows_powercfg_xml_condition_poor(tmp_path):
    from system_info.health import _parse_battery_xml

    path = _write_battery_report_xml(
        tmp_path, _battery_xml_node(design=6500, full=2599, cycle=400)
    )
    batt = _parse_battery_xml(path)
    assert batt is not None
    assert batt.health_percent == 40
    assert batt.condition == "Poor"


def test_health_windows_powercfg_xml_malformed_returns_none(tmp_path):
    from system_info.health import _parse_battery_xml

    path = tmp_path / "broken.xml"
    path.write_text("<BatteryReport><Batteries></BatteryReport>", encoding="utf-8")
    assert _parse_battery_xml(path) is None


def test_health_windows_powercfg_xml_missing_file_returns_none(tmp_path):
    from system_info.health import _parse_battery_xml

    assert _parse_battery_xml(tmp_path / "does-not-exist.xml") is None


def test_health_windows_wmi_cycle_count_zero(monkeypatch):
    from system_info.health import _collect_windows_battery

    monkeypatch.setattr(
        "system_info.health._collect_windows_battery_powercfg", lambda: None
    )
    payload = {
        "FullChargedCapacity": 6500,
        "DesignedCapacity": 6500,
        "CycleCount": 0,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.cycle_count == 0
    assert batt.health_percent == 100
    assert batt.condition == "Good"


def test_health_windows_wmi_cycle_count_acpi_sentinel(monkeypatch):
    from system_info.health import _collect_windows_battery

    monkeypatch.setattr(
        "system_info.health._collect_windows_battery_powercfg", lambda: None
    )
    payload = {
        "FullChargedCapacity": 5577,
        "DesignedCapacity": 6500,
        "CycleCount": 4294967295,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.cycle_count is None
    assert batt.health_percent == 86
    assert batt.condition == "Good"


def test_health_windows_wmi_missing_capacity_unknown_condition(monkeypatch):
    from system_info.health import _collect_windows_battery

    monkeypatch.setattr(
        "system_info.health._collect_windows_battery_powercfg", lambda: None
    )
    payload = {
        "FullChargedCapacity": None,
        "DesignedCapacity": None,
        "CycleCount": 12,
    }
    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(payload),
    )
    batt = _collect_windows_battery()
    assert batt is not None
    assert batt.cycle_count == 12
    assert batt.health_percent is None
    assert batt.condition is None


def test_health_battery_condition_helper():
    from system_info.health import _battery_condition

    assert _battery_condition(None) is None
    assert _battery_condition(80) == "Good"
    assert _battery_condition(100) == "Good"
    assert _battery_condition(79) == "Warning"
    assert _battery_condition(60) == "Warning"
    assert _battery_condition(59) == "Poor"
    assert _battery_condition(0) == "Poor"


def test_health_windows_sas_disk_is_internal(monkeypatch):
    from system_info.health import _collect_windows_disks

    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(_windows_disk_payload("SAS")),
    )
    disks = _collect_windows_disks()
    assert len(disks) == 1
    assert disks[0].internal is True


def test_health_windows_usb_disk_is_external(monkeypatch):
    from system_info.health import _collect_windows_disks

    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(_windows_disk_payload("USB")),
    )
    disks = _collect_windows_disks()
    assert len(disks) == 1
    assert disks[0].internal is False


def test_health_windows_unknown_bus_type_internal_none(monkeypatch):
    from system_info.health import _collect_windows_disks

    monkeypatch.setattr(
        "system_info.health._run",
        lambda cmd, timeout=15.0: json.dumps(_windows_disk_payload("Unknown")),
    )
    disks = _collect_windows_disks()
    assert len(disks) == 1
    assert disks[0].internal is None
