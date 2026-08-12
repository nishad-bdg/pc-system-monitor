from __future__ import annotations

_VIRTUAL_TOKENS = (
    "hyper-v",
    "vethernet",
    "docker",
    "wsl",
    "vmware",
    "virtualbox",
    "vbox",
    "vpn",
    "tap-windows",
    "wireguard",
    "nordlynx",
    "bluetooth",
    "virtual",
    "pseudo",
)

_LOOPBACK_TOKENS = ("loopback",)


def _haystack(name: str, description: str | None) -> str:
    return f"{name} {description or ''}".lower()


def is_loopback(name: str, description: str | None = None) -> bool:
    text = _haystack(name, description)
    if name.strip().lower() == "lo":
        return True
    return any(token in text for token in _LOOPBACK_TOKENS)


def is_virtual_adapter(
    name: str,
    description: str | None = None,
    adapter_type: str | None = None,
) -> bool:
    if is_loopback(name, description):
        return True
    if adapter_type in {"vpn", "bluetooth", "virtual", "loopback"}:
        return True
    text = _haystack(name, description)
    return any(token in text for token in _VIRTUAL_TOKENS)


def infer_adapter_type(
    name: str,
    description: str | None = None,
    media_type: str | None = None,
) -> str:
    if is_loopback(name, description):
        return "loopback"
    text = _haystack(name, description)
    media = (media_type or "").lower()
    if "bluetooth" in text:
        return "bluetooth"
    if "vpn" in text or "wireguard" in text or "nordlynx" in text:
        return "vpn"
    if "wi-fi" in text or "wifi" in text or "802.11" in media or "wlan" in text:
        return "wifi"
    if "ethernet" in text or "802.3" in media:
        return "ethernet"
    if is_virtual_adapter(name, description):
        return "virtual"
    return "other"
