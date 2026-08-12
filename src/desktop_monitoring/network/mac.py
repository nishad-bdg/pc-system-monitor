from __future__ import annotations

import re

_HEX_MAC = re.compile(r"^[0-9A-F]{12}$")
_INVALID = {"000000000000", "FFFFFFFFFFFF"}


def normalize_mac(value: str | None) -> str | None:
    """Return MAC as AA:BB:CC:DD:EE:FF, or None if missing/invalid."""
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", value.strip())
    if len(cleaned) != 12:
        return None
    upper = cleaned.upper()
    if not _HEX_MAC.match(upper) or upper in _INVALID:
        return None
    parts = [upper[i : i + 2] for i in range(0, 12, 2)]
    return ":".join(parts)


def is_randomized_or_locally_administered(mac: str | None) -> bool:
    """True when IEEE U/L bit (0x02) is set on the first octet."""
    normalized = normalize_mac(mac)
    if normalized is None:
        return False
    first_octet = int(normalized[0:2], 16)
    return bool(first_octet & 0x02)
