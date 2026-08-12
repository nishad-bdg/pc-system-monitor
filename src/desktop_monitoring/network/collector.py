from __future__ import annotations

from dataclasses import replace
from typing import Any

from desktop_monitoring.network.classify import (
    infer_adapter_type,
    is_loopback,
    is_virtual_adapter,
)
from desktop_monitoring.network.mac import normalize_mac
from desktop_monitoring.network.models import Adapter, adapter_to_dict, empty_bandwidth
from desktop_monitoring.network.select import (
    select_preferred_adapter,
    select_primary_mac,
)


def _empty_preferred_adapter() -> dict[str, Any]:
    return {
        "name": None,
        "description": None,
        "interface_index": None,
        "interface_guid": None,
        "adapter_type": None,
        "is_physical": False,
        "is_virtual": False,
        "is_active": False,
        "is_connected": False,
        "is_preferred": False,
        "current_mac_address": None,
        "permanent_mac_address": None,
        "is_randomized_or_locally_administered": False,
        "ipv4_addresses": [],
        "ipv6_addresses": [],
        "subnet_mask": None,
        "default_gateway": None,
        "dns_servers": [],
        "ssid": None,
        "link_speed_mbps": None,
    }


def build_network_payload(
    adapters: list[Adapter],
    connection_hint: str | None = None,
) -> dict[str, Any]:
    normalized = [adapter.normalized() for adapter in adapters]
    preferred = select_preferred_adapter(normalized)
    preferred_payload = (
        adapter_to_dict(preferred) if preferred else _empty_preferred_adapter()
    )
    all_adapters = [adapter_to_dict(adapter) for adapter in normalized]
    active_adapters = [
        adapter_to_dict(adapter) for adapter in normalized if adapter.is_active
    ]
    physical_count = sum(
        1
        for adapter in normalized
        if adapter.is_physical
        and not adapter.is_virtual
        and not is_loopback(adapter.name, adapter.description)
    )
    local_ipv4 = (
        preferred.ipv4_addresses[0]
        if preferred is not None and preferred.ipv4_addresses
        else None
    )
    connection_type = (
        connection_hint
        if connection_hint is not None
        else preferred.adapter_type if preferred is not None else None
    )

    return {
        "connection_type": connection_type,
        "local_ipv4": local_ipv4,
        "primary_mac_address": select_primary_mac(normalized),
        "preferred_adapter": preferred_payload,
        "physical_adapter_count": physical_count,
        "active_adapter_count": len(active_adapters),
        "active_adapters": active_adapters,
        "all_adapters": all_adapters,
        "bandwidth": empty_bandwidth(),
    }


def _map_powershell_adapter(
    raw: dict[str, Any],
    preferred_index: int | None,
) -> Adapter:
    name = raw.get("Name") or ""
    description = raw.get("InterfaceDescription")
    adapter_type = infer_adapter_type(name, description, raw.get("MediaType"))
    loopback = is_loopback(name, description)
    hardware_interface = raw.get("HardwareInterface")
    virtual = is_virtual_adapter(name, description, adapter_type) or (
        hardware_interface is False and not loopback
    )
    connected = (raw.get("Status") or "").lower() == "up"
    interface_index = raw.get("ifIndex")

    return Adapter(
        name=name,
        description=description,
        interface_index=interface_index,
        interface_guid=(
            str(raw["InterfaceGuid"]) if raw.get("InterfaceGuid") else None
        ),
        adapter_type=adapter_type,
        is_physical=(
            hardware_interface is not False and not virtual and not loopback
        ),
        is_virtual=virtual,
        is_active=connected,
        is_connected=connected,
        is_preferred=(
            preferred_index is not None and interface_index == preferred_index
        ),
        current_mac_address=normalize_mac(raw.get("MacAddress")),
        permanent_mac_address=normalize_mac(raw.get("PermanentAddress")),
        link_speed_mbps=_parse_link_speed(raw.get("LinkSpeed")),
    )


def _parse_link_speed(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).lower().replace(",", "")
    try:
        number = float(text.split()[0])
    except (ValueError, IndexError):
        return None
    return number * 1000.0 if "gbps" in text else number


def _extract_addresses(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [
        item["IPAddress"]
        for item in value
        if isinstance(item, dict) and item.get("IPAddress")
    ]


def _extract_gateway(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("NextHop")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("NextHop"):
                return item["NextHop"]
    return None


def collect_network() -> dict[str, Any]:
    """Collect live Windows network data, falling back to an empty payload."""
    from desktop_monitoring.network import powershell

    try:
        preferred_index = powershell.fetch_default_route_interface_index()
    except Exception:
        preferred_index = None

    try:
        raw_adapters = powershell.fetch_net_adapters()
    except Exception:
        return build_network_payload([])

    adapters = [
        _map_powershell_adapter(raw, preferred_index) for raw in raw_adapters
    ]
    try:
        configurations = powershell.fetch_net_ip_configuration()
    except Exception:
        configurations = []

    by_index = {
        config.get("InterfaceIndex"): config
        for config in configurations
        if config.get("InterfaceIndex") is not None
    }
    enriched: list[Adapter] = []
    for adapter in adapters:
        config = by_index.get(adapter.interface_index)
        if config is None:
            enriched.append(adapter)
            continue
        enriched.append(
            replace(
                adapter,
                ipv4_addresses=_extract_addresses(config.get("IPv4Address")),
                ipv6_addresses=_extract_addresses(config.get("IPv6Address")),
                default_gateway=_extract_gateway(
                    config.get("IPv4DefaultGateway")
                ),
            )
        )

    return build_network_payload(enriched)
