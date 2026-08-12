import argparse
import json
import os

import requests

from .geo import geo_locate
from .ip import get_private_ip, get_public_ip, get_mac_address, get_mac_addresses
from .os_info import collect_os_info
from .resources import collect_resources
from .disk import collect_disk_info
from .printers import collect_printers
from .device import get_or_create_device_id, resolve_pc_name

DEFAULT_API_URL = os.getenv("SYSTEM_INFO_API_URL", "http://127.0.0.1:8000")
DEFAULT_API_KEY = os.getenv("SYSTEM_INFO_API_KEY", "")
DEFAULT_PC_NAME = os.getenv("SYSTEM_INFO_PC_NAME", "")
SAVE_TIMEOUT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-info",
        description="Show IP address, geolocation and OS info (macOS & Windows).",
    )
    parser.add_argument("--os", action="store_true", help="Only show OS info")
    parser.add_argument("--ip", action="store_true", help="Only show IP addresses")
    parser.add_argument("--geo", action="store_true", help="Only show geolocation")
    parser.add_argument("--sys", action="store_true", help="Only show CPU/RAM usage")
    parser.add_argument("--disk", action="store_true", help="Only show storage/disk info")
    parser.add_argument("--printers", action="store_true", help="Only show printers")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not save report to the API")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL to save reports to")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for authenticated save")
    parser.add_argument(
        "--pc-name",
        default=DEFAULT_PC_NAME,
        help="Custom PC name (Windows only; macOS always uses hostname). "
        "Falls back to hostname when empty. Env: SYSTEM_INFO_PC_NAME",
    )
    return parser


def _fmt_bytes(num: int) -> str:
    size = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024


def run(args: argparse.Namespace) -> int:
    data: dict = {}

    specific = args.ip or args.geo or args.sys or args.disk or args.printers or args.os
    show_os = not specific or args.os
    show_ip = not specific or args.ip
    show_geo = not specific or args.geo
    show_sys = not specific or args.sys
    show_disk = not specific or args.disk
    show_printers = not specific or args.printers

    pc_name = resolve_pc_name(args.pc_name)
    device_id = get_or_create_device_id(pc_name)
    data["pc_name"] = pc_name
    data["device_id"] = device_id

    if show_os:
        data["os"] = collect_os_info().to_dict()

    public_ip = get_public_ip() if (show_ip or show_geo) else None
    if show_ip:
        data["private_ip"] = get_private_ip()
        data["public_ip"] = public_ip
        data["mac_address"] = get_mac_address()
        data["mac_addresses"] = get_mac_addresses()

    location = geo_locate(public_ip) if (show_geo and public_ip) else None
    data["location"] = location.to_dict() if location else None

    if show_sys:
        data["resources"] = collect_resources().to_dict()

    if show_disk:
        data["disk"] = collect_disk_info().to_dict()

    if show_printers:
        data["printers"] = collect_printers().to_dict()

    _print(data, show_os, show_ip, show_geo, show_sys, show_disk, show_printers, args)

    if not args.no_save:
        saved_id = save_report(data, args.api_url, args.api_key)
        if saved_id and not args.json:
            print(f"\n[saved] report {saved_id} -> {args.api_url}")
        elif not saved_id and not args.json and args.api_key:
            print("\n[save] failed - check API URL and API key")
    return 0


def save_report(data: dict, api_url: str, api_key: str = "") -> str | None:
    """POST the collected report to the FastAPI backend. Returns id or None."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/reports",
            json=data,
            headers=headers,
            timeout=SAVE_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("id")
    except (requests.RequestException, ValueError, OSError) as exc:
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print(f"[save] failed: {exc}")
        return None


def _print(
    data: dict,
    show_os: bool,
    show_ip: bool,
    show_geo: bool,
    show_sys: bool,
    show_disk: bool,
    show_printers: bool,
    args: argparse.Namespace,
) -> None:
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    print("== Device ==")
    print(f"  pc_name:   {data.get('pc_name') or 'unknown'}")
    print(f"  device_id: {data.get('device_id') or 'unknown'}")

    if show_os:
        print("== OS Info ==")
        for key, value in data["os"].items():
            print(f"  {key}: {value}")

    if show_ip:
        print("== IP Addresses ==")
        print(f"  private_ip: {data['private_ip']}")
        print(f"  public_ip:  {data['public_ip'] or 'unknown'}")
        print("== Network Interfaces ==")
        print(f"  primary mac: {data['mac_address'] or 'unknown'}")
        for iface in data["mac_addresses"]:
            print(f"  {iface['interface']}: {iface['mac']}")

    if show_geo:
        print("== Geolocation ==")
        loc = data["location"]
        if loc:
            for key, value in loc.items():
                print(f"  {key}: {value}")
        else:
            print("  unavailable")

    if show_sys:
        res = data["resources"]
        print("== CPU ==")
        print(f"  cores:      {res['cpu_count']} logical / {res['cpu_count_physical']} physical")
        print(f"  usage:      {res['cpu_percent']:.1f}%")
        freq = res["cpu_freq_mhz"]
        print(f"  frequency:  {freq:.0f} MHz" if freq else "  frequency:  unknown")
        print("== Memory (RAM) ==")
        print(f"  total:      {_fmt_bytes(res['ram_total'])}")
        print(f"  used:       {_fmt_bytes(res['ram_used'])}")
        print(f"  available:  {_fmt_bytes(res['ram_available'])}")
        print(f"  free:       {_fmt_bytes(res['ram_free'])}")
        print(f"  usage:      {res['ram_percent']:.1f}%")
        print("== Swap ==")
        print(f"  total:      {_fmt_bytes(res['swap_total'])}")
        print(f"  used:       {_fmt_bytes(res['swap_used'])}")
        print(f"  usage:      {res['swap_percent']:.1f}%")

    if show_disk:
        disk = data["disk"]
        print("== Storage Devices ==")
        print(f"  {'device':<16}{'total':>12}{'used':>12}{'free':>12}  {'usage':>6}")
        for d in disk["devices"]:
            print(
                f"  {d['device']:<16}"
                f"{_fmt_bytes(d['total']):>12}"
                f"{_fmt_bytes(d['used']):>12}"
                f"{_fmt_bytes(d['free']):>12}"
                f"  {d['percent']:>5.1f}%"
            )
        print("== Disk Partitions ==")
        print(
            f"  {'device':<16}{'mountpoint':<30}{'fstype':<6}"
            f"{'total':>12}{'used':>12}{'free':>12}  {'usage':>6}"
        )
        for p in disk["partitions"]:
            print(
                f"  {p['device']:<16}{p['mountpoint']:<30}{p['fstype']:<6}"
                f"{_fmt_bytes(p['total']):>12}"
                f"{_fmt_bytes(p['used']):>12}"
                f"{_fmt_bytes(p['free']):>12}"
                f"  {p['percent']:>5.1f}%"
            )

    if show_printers:
        printers = data.get("printers") or {}
        print("== Printers ==")
        print(f"  count: {printers.get('count', 0)}")
        for label in ("usb", "network", "other"):
            items = printers.get(label) or []
            print(f"  {label}: {len(items)}")
            for item in items:
                print(f"    - {item.get('name')} ({item.get('port') or 'unknown'})")


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
