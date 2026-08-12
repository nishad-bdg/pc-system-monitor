import argparse
import json

from .geo import geo_locate
from .ip import get_private_ip, get_public_ip
from .os_info import collect_os_info


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-info",
        description="Show IP address, geolocation and OS info (macOS & Windows).",
    )
    parser.add_argument("--os", action="store_true", help="Only show OS info")
    parser.add_argument("--ip", action="store_true", help="Only show IP addresses")
    parser.add_argument("--geo", action="store_true", help="Only show geolocation")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    return parser


def run(args: argparse.Namespace) -> int:
    data: dict = {}

    show_os = not (args.ip or args.geo) or args.os
    show_ip = not (args.os or args.geo) or args.ip
    show_geo = not (args.os or args.ip) or args.geo

    if show_os:
        data["os"] = collect_os_info().to_dict()

    public_ip = get_public_ip() if (show_ip or show_geo) else None
    if show_ip:
        data["private_ip"] = get_private_ip()
        data["public_ip"] = public_ip

    location = geo_locate(public_ip) if (show_geo and public_ip) else None
    data["location"] = location.to_dict() if location else None

    _print(data, show_os, show_ip, show_geo, args)
    return 0


def _print(data: dict, show_os: bool, show_ip: bool, show_geo: bool, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    if show_os:
        print("== OS Info ==")
        for key, value in data["os"].items():
            print(f"  {key}: {value}")

    if show_ip:
        print("== IP Addresses ==")
        print(f"  private_ip: {data['private_ip']}")
        print(f"  public_ip:  {data['public_ip'] or 'unknown'}")

    if show_geo:
        print("== Geolocation ==")
        loc = data["location"]
        if loc:
            for key, value in loc.items():
                print(f"  {key}: {value}")
        else:
            print("  unavailable")


def main() -> int:
    args = build_parser().parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
