from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from desktop_monitoring.network.mac import (
    is_randomized_or_locally_administered,
    normalize_mac,
)


@dataclass
class Adapter:
    name: str
    description: str | None = None
    interface_index: int | None = None
    interface_guid: str | None = None
    adapter_type: str = "other"
    is_physical: bool = False
    is_virtual: bool = False
    is_active: bool = False
    is_connected: bool = False
    is_preferred: bool = False
    current_mac_address: str | None = None
    permanent_mac_address: str | None = None
    ipv4_addresses: list[str] = field(default_factory=list)
    ipv6_addresses: list[str] = field(default_factory=list)
    subnet_mask: str | None = None
    default_gateway: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    ssid: str | None = None
    link_speed_mbps: float | None = None

    def normalized(self) -> Adapter:
        current = normalize_mac(self.current_mac_address)
        permanent = normalize_mac(self.permanent_mac_address)
        return Adapter(
            **{
                **asdict(self),
                "current_mac_address": current,
                "permanent_mac_address": permanent,
            }
        )


def adapter_to_dict(adapter: Adapter) -> dict[str, Any]:
    normalized = adapter.normalized()
    payload = asdict(normalized)
    payload["is_randomized_or_locally_administered"] = (
        is_randomized_or_locally_administered(normalized.current_mac_address)
    )
    return payload


def empty_bandwidth() -> dict[str, Any]:
    return {
        "since_previous_collection": {},
        "since_system_boot": {},
        "application_observed_cumulative": {},
        "per_interface": [],
    }
