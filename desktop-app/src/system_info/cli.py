import argparse
import json
import os

import requests

from .version import __version__
from .config import load_install_config
from .geo import geo_locate
from .ip import get_private_ip, get_public_ip, get_mac_address, get_mac_addresses
from .os_info import collect_os_info
from .resources import collect_resources
from .disk import collect_disk_info
from .printers import collect_printers
from .network import collect_network_usage
from .uptime import collect_uptime
from .security import collect_security_info
from .health import collect_health_info
from .email_accounts import collect_email_accounts
from .device import get_or_create_device_id, resolve_pc_name
from .startup import register_startup, unregister_startup
from .update import check_for_update, maybe_auto_update
from .print_jobs import (
    collect_new_print_events,
    save_state as save_print_state,
    send_print_events,
)
# Load packaged/installer config before reading defaults.
load_install_config()

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
    parser.add_argument("--network", action="store_true", help="Only show network bandwidth")
    parser.add_argument("--security", action="store_true", help="Only show internet-security software")
    parser.add_argument("--health", action="store_true", help="Only show storage/battery health")
    parser.add_argument("--emails", action="store_true", help="Only show configured POP/IMAP email accounts")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not save report to the API")
    parser.add_argument("--heartbeat", action="store_true", help="Only send a lightweight online heartbeat, then exit")
    parser.add_argument("--print-jobs", action="store_true", help="Flush newly completed print jobs to the API, then exit")
    parser.add_argument("--watch", action="store_true", help="Run continuously in the background (messenger-style): heartbeats, print jobs, hourly reports and a tray Exit on Windows")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL to save reports to")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for authenticated save")
    parser.add_argument(
        "--pc-name",
        default=DEFAULT_PC_NAME,
        help="Custom PC name (Windows only; macOS always uses hostname). "
        "Falls back to hostname when empty. Env: SYSTEM_INFO_PC_NAME",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check SYSTEM_INFO_UPDATE_URL for a newer Windows release and exit",
    )
    parser.add_argument(
        "--auto-update",
        action="store_true",
        help="If a newer Windows release exists, download and stage it (frozen builds)",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    return parser


def _fmt_bytes(num: int) -> str:
    size = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def run(args: argparse.Namespace) -> int:
    if args.version:
        print(__version__)
        return 0

    # First-run auto-start: on Windows installs the app registers itself to
    # run --watch at every logon (skipped with SYSTEM_INFO_NO_STARTUP=1).
    if os.getenv("SYSTEM_INFO_NO_STARTUP") != "1":
        register_startup()

    if args.watch or _default_to_watch(args):
        from .watch import run_watch

        return run_watch(args)

    if args.check_update or args.auto_update:
        manifest = check_for_update()
        if not manifest:
            if not args.json:
                print(f"up to date ({__version__})")
            else:
                print(json.dumps({"version": __version__, "update": None}))
            return 0
        if args.json:
            print(json.dumps({"version": __version__, "update": manifest}, indent=2))
        else:
            print(f"update available: {manifest.get('version')} (local {__version__})")
        if args.auto_update:
            started = maybe_auto_update(quiet=bool(args.json))
            return 0 if started else 1
        return 0

    # Quiet release check on normal scheduled runs (Windows frozen builds).
    if os.getenv("SYSTEM_INFO_UPDATE_URL") and not args.no_save and not args.heartbeat:
        maybe_auto_update(quiet=True)

    if args.heartbeat:
        pc_name = resolve_pc_name(args.pc_name)
        device_id = get_or_create_device_id(pc_name)
        sync_print_jobs(args, device_id, pc_name, quiet=True)
        payload = {"device_id": device_id, "pc_name": pc_name}
        response = send_heartbeat(payload, args.api_url, args.api_key)
        if response:
            from .commands import handle_pending_commands

            try:
                handle_pending_commands(
                    response.get("commands"), args.api_url, args.api_key
                )
            except Exception:
                pass
        ok = response is not None
        if args.json:
            print(json.dumps({"heartbeat": "ok" if ok else "failed"}))
        elif ok:
            print(f"[heartbeat] {device_id} {pc_name} -> {args.api_url}")
        else:
            print("\n[heartbeat] failed - check API URL and API key")
            return 1
        return 0

    if args.print_jobs:
        pc_name = resolve_pc_name(args.pc_name)
        device_id = get_or_create_device_id(pc_name)
        sent = sync_print_jobs(args, device_id, pc_name)
        if args.json:
            print(json.dumps({"print_jobs": sent}))
        else:
            print(f"[print] flushed {sent} new print job(s)")
        return 0

    data = collect_all(args)

    show_os = args.os or not specific(args)
    show_ip = args.ip or not specific(args)
    show_geo = args.geo or not specific(args)
    show_sys = args.sys or not specific(args)
    show_disk = args.disk or not specific(args)
    show_printers = args.printers or not specific(args)
    show_network = args.network or not specific(args)
    show_security = args.security or not specific(args)
    show_health = args.health or not specific(args)
    show_emails = args.emails or not specific(args)

    _print(
        data,
        show_os,
        show_ip,
        show_geo,
        show_sys,
        show_disk,
        show_printers,
        show_network,
        show_security,
        show_health,
        show_emails,
        args,
    )

    if not args.no_save:
        saved_id = save_report(data, args.api_url, args.api_key)
        if saved_id and not args.json:
            print(f"\n[saved] report {saved_id} -> {args.api_url}")
        elif not saved_id and not args.json and args.api_key:
            print("\n[save] failed - check API URL and API key")
    return 0


def specific(args: argparse.Namespace) -> bool:
    return (
        args.ip
        or args.geo
        or args.sys
        or args.disk
        or args.printers
        or args.network
        or args.security
        or args.health
        or args.emails
        or args.os
    )


def _default_to_watch(args: argparse.Namespace) -> bool:
    """Frozen Windows builds with no one-shot flags stay in the system tray."""
    if getattr(args, "watch", False):
        return False
    from .config import is_frozen

    if os.name != "nt" or not is_frozen():
        return False
    one_shot = (
        args.heartbeat
        or args.print_jobs
        or args.check_update
        or args.auto_update
        or args.version
        or args.json
        or specific(args)
    )
    return not one_shot


def collect_all(args: argparse.Namespace) -> dict:
    """Gather the full data payload (all sections) — shared by one-shot and --watch runs."""
    data: dict = {}

    if args.os or not specific(args):
        data["os"] = collect_os_info().to_dict()

    show_ip = args.ip or not specific(args)
    show_geo = args.geo or not specific(args)
    public_ip = get_public_ip() if (show_ip or show_geo) else None
    if show_ip:
        data["private_ip"] = get_private_ip()
        data["public_ip"] = public_ip
        data["mac_address"] = get_mac_address()
        data["mac_addresses"] = get_mac_addresses()

    location = geo_locate(public_ip) if (show_geo and public_ip) else None
    data["location"] = location.to_dict() if location else None

    if args.sys or not specific(args):
        data["resources"] = collect_resources().to_dict()
        data["uptime"] = collect_uptime().to_dict()

    if args.disk or not specific(args):
        data["disk"] = collect_disk_info().to_dict()

    if args.printers or not specific(args):
        data["printers"] = collect_printers().to_dict()

    if args.network or not specific(args):
        data["network"] = collect_network_usage().to_dict()

    if args.security or not specific(args):
        data["security"] = collect_security_info().to_dict()

    if args.health or not specific(args):
        data["health"] = collect_health_info().to_dict()

    if args.emails or not specific(args):
        data["email_accounts"] = collect_email_accounts().to_dict()

    pc_name = resolve_pc_name(args.pc_name)
    device_id = get_or_create_device_id(pc_name)
    data["pc_name"] = pc_name
    data["device_id"] = device_id
    return data


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


def send_heartbeat(data: dict, api_url: str, api_key: str = "") -> dict | None:
    """POST a lightweight online heartbeat to the API.

    Returns the parsed JSON response (which includes any pending remote
    commands for this device), or None on failure.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/heartbeat",
            json=data,
            headers=headers,
            timeout=SAVE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError, OSError) as exc:
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print(f"[heartbeat] failed: {exc}")
        return None


def sync_print_jobs(
    args: argparse.Namespace,
    device_id: str,
    pc_name: str,
    quiet: bool = False,
) -> int:
    """Collect newly completed print jobs and POST them to the API.

    Always advances the local watermark (state), even when the API is down,
    so already-seen jobs are not re-reported. Returns the number of events
    flushed (reported) this run.
    """
    events, state = collect_new_print_events()
    save_print_state(state)
    if not events:
        return 0
    ok = send_print_events(
        events,
        args.api_url,
        args.api_key,
        device_id=device_id,
        pc_name=pc_name,
    )
    if not ok and not quiet:
        print("[print] could not reach API")
    return len(events)


def _print(
    data: dict,
    show_os: bool,
    show_ip: bool,
    show_geo: bool,
    show_sys: bool,
    show_disk: bool,
    show_printers: bool,
    show_network: bool,
    show_security: bool,
    show_health: bool,
    show_emails: bool,
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
        ram_speed = res.get("ram_speed_mhz")
        ram_type = res.get("ram_type")
        if ram_speed:
            print(f"  bus speed:  {ram_speed} MHz")
        if ram_type:
            print(f"  type:       {ram_type}")
        print("== Swap ==")
        print(f"  total:      {_fmt_bytes(res['swap_total'])}")
        print(f"  used:       {_fmt_bytes(res['swap_used'])}")
        print(f"  usage:      {res['swap_percent']:.1f}%")
        battery = res.get("battery")
        if battery:
            plugged = "plugged in" if battery.get("power_plugged") else "on battery"
            secs = battery.get("seconds_left")
            remaining = f" · {_fmt_duration(secs)} remaining" if secs is not None else ""
            print("== Battery ==")
            print(f"  charge:     {battery['percent']:.0f}% ({plugged}){remaining}")
        uptime = data.get("uptime") or {}
        print("== Uptime ==")
        print(f"  session:    {_fmt_duration(float(uptime.get('uptime_seconds') or 0))}")
        print(f"  day tz:     {uptime.get('day_timezone') or 'UTC'}")
        by_day = uptime.get("by_day") or {}
        if by_day:
            for day, seconds in sorted(by_day.items())[-14:]:
                print(f"  {day}: {_fmt_duration(float(seconds))}")
        else:
            print("  by_day:     (none yet)")

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

    if show_network:
        net = data.get("network") or {}
        print("== Network Bandwidth ==")
        print(f"  sent total:     {_fmt_bytes(int(net.get('bytes_sent') or 0))}")
        print(f"  received total: {_fmt_bytes(int(net.get('bytes_recv') or 0))}")
        print(f"  send rate:      {_fmt_bytes(int(net.get('send_rate_bps') or 0))}/s")
        print(f"  recv rate:      {_fmt_bytes(int(net.get('recv_rate_bps') or 0))}/s")

    if show_printers:
        printers = data.get("printers") or {}
        print("== Printers ==")
        print(f"  count: {printers.get('count', 0)}")
        for label in ("usb", "network", "other"):
            items = printers.get(label) or []
            print(f"  {label}: {len(items)}")
            for item in items:
                extra = []
                if item.get("ip"):
                    extra.append(f"ip={item['ip']}")
                if item.get("print_count") is not None:
                    extra.append(f"prints={item['print_count']}")
                suffix = f" [{', '.join(extra)}]" if extra else ""
                print(f"    - {item.get('name')} ({item.get('port') or 'unknown'}){suffix}")

    if show_security:
        security = data.get("security") or {}
        installed = security.get("installed") or []
        print("== Internet Security ==")
        if installed:
            for product in installed:
                name = product.get("name")
                vendor = product.get("vendor")
                active = product.get("active")
                state = ""
                if active is True:
                    state = " [active]"
                elif active is False:
                    state = " [inactive]"
                expiry = ""
                if product.get("expired"):
                    expiry = " [Expired]"
                elif product.get("expiry_date"):
                    days = product.get("days_remaining")
                    if days is None:
                        expiry = f" [expires {product.get('expiry_date')}]"
                    else:
                        unit = "day" if days == 1 else "days"
                        expiry = f" [{days} {unit} remaining, expires {product.get('expiry_date')}]"
                print(f"  - {name} ({vendor}){state}{expiry}")
        else:
            print("  none detected")

    if show_health:
        health = data.get("health") or {}
        disks = health.get("disks") or []
        print("== Storage Health ==")
        if disks:
            for d in disks:
                print(
                    f"  - {d.get('name')}"
                    f" [{d.get('media_type') or 'unknown'}]"
                    f" health={d.get('health') or 'unknown'}"
                    + (f" smart={d.get('smart_status')}" if d.get("smart_status") else "")
                )
        else:
            print("  none detected")
        battery = health.get("battery")
        print("== Battery Health ==")
        if battery:
            print(f"  condition:     {battery.get('condition') or 'unknown'}")
            print(f"  health:        {battery.get('health_percent')}%" if battery.get("health_percent") is not None else "  health:        unknown")
            print(f"  cycle count:   {battery.get('cycle_count')}" if battery.get("cycle_count") is not None else "  cycle count:   unknown")
        else:
            print("  no battery detected")

    if show_emails:
        emails = data.get("email_accounts") or {}
        accounts = emails.get("accounts") or []
        print("== Email Accounts ==")
        if accounts:
            for acc in accounts:
                parts = [
                    f"client={acc.get('client') or 'unknown'}",
                    f"protocol={acc.get('protocol') or 'unknown'}",
                ]
                if acc.get("incoming_host"):
                    parts.append(f"in={acc.get('incoming_host')}:{acc.get('incoming_port') or '?'}")
                if acc.get("outgoing_host"):
                    parts.append(f"out={acc.get('outgoing_host')}:{acc.get('outgoing_port') or '?'}")
                if acc.get("security"):
                    parts.append(f"security={acc.get('security')}")
                suffix = f" [{', '.join(parts)}]" if parts else ""
                label = acc.get("email") or acc.get("username") or "unknown"
                print(f"  - {label}{suffix}")
        else:
            print("  none detected")


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
