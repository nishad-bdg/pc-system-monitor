import socket

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
