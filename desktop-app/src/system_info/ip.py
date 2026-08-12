import socket
import uuid

import psutil
import requests

PUBLIC_IP_URL = "https://api.ipify.org"
PUBLIC_IP_TIMEOUT = 5
PRIVATE_IP_PLACEHOLDER_FAMILIES = (None, "0.0.0.0", "127.0.0.1")


def get_private_ip() -> str:
    """Best-effort private IP of this host. Portable across macOS and Windows."""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and ip not in PRIVATE_IP_PLACEHOLDER_FAMILIES:
            return ip
    except OSError:
        pass

    # Fallback: connect a UDP socket (never sends packets) to infer the egress IP.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass

    return "unknown"


def get_public_ip() -> str | None:
    """Return the public IP via ipify, or None on failure."""
    try:
        resp = requests.get(PUBLIC_IP_URL, timeout=PUBLIC_IP_TIMEOUT)
        resp.raise_for_status()
        return resp.text.strip() or None
    except (requests.RequestException, OSError):
        return None
    except ValueError:
        return None


def _format_mac(raw: int) -> str:
    return ":".join(f"{(raw >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


def get_mac_addresses() -> list[dict]:
    """List per-interface MAC addresses (AF_LINK). Portable mac/Windows/Linux."""
    interfaces: list[dict] = []
    seen: set = set()
    for iface, snics in psutil.net_if_addrs().items():
        for snic in snics:
            if snic.family != psutil.AF_LINK or not snic.address:
                continue
            mac = snic.address.lower().replace("-", ":")
            if mac in seen or set(mac.replace(":", "")) == {"0"}:
                continue
            seen.add(mac)
            interfaces.append({"interface": iface, "mac": mac})
    return sorted(interfaces, key=lambda i: i["interface"])


def get_mac_address() -> str | None:
    """Primary MAC address (Node's global ID), falling back to first interface."""
    node = uuid.getnode()
    if node and node != 0xFFFFFFFFFFFF:
        mac = _format_mac(node)
        if set(mac.replace(":", "")) != {"0"}:
            return mac
    addresses = get_mac_addresses()
    return addresses[0]["mac"] if addresses else None
