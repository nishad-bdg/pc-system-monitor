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
                          ram_percent=50.0, swap_total=2048, swap_used=0, swap_percent=0.0)
    assert set(loc.to_dict()) == {
        "cpu_count", "cpu_count_physical", "cpu_percent", "cpu_freq_mhz",
        "ram_total", "ram_used", "ram_available", "ram_free", "ram_percent",
        "swap_total", "swap_used", "swap_percent",
    }


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


def test_collect_network_usage(monkeypatch):
    from system_info import network

    class Counters:
        def __init__(self, sent, recv):
            self.bytes_sent = sent
            self.bytes_recv = recv

    values = iter([Counters(1000, 2000), Counters(1500, 2600)])
    monkeypatch.setattr(network.psutil, "net_io_counters", lambda: next(values))
    monkeypatch.setattr(network.time, "sleep", lambda s: None)
    monkeypatch.setattr(network, "measure_download_mbps", lambda: 42.5)
    usage = network.collect_network_usage(interval=0.5)
    assert usage.bytes_sent == 1500
    assert usage.bytes_recv == 2600
    assert usage.send_rate_bps == 1000.0  # 500 bytes / 0.5s
    assert usage.recv_rate_bps == 1200.0
    assert usage.download_mbps == 42.5
    assert usage.upload_mbps is None
    d = usage.to_dict()
    assert d["download_mbps"] == 42.5
    assert d["upload_mbps"] is None


def test_measure_download_mbps(monkeypatch):
    from system_info import network

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536):
            yield b"x" * 1_000_000

    times = iter([100.0, 100.5])  # 0.5s for 1_000_000 bytes → 16 Mbps
    monkeypatch.setattr(network.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        network.requests,
        "get",
        lambda *a, **k: FakeResp(),
    )
    mbps = network.measure_download_mbps()
    assert mbps is not None
    assert abs(mbps - 16.0) < 0.01


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
        swap_total=2048, swap_used=0, swap_percent=0.0))
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
