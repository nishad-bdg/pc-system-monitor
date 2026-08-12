from __future__ import annotations

from desktop_monitoring.network.mac import normalize_mac
from desktop_monitoring.network.models import Adapter


def _mac_of(adapter: Adapter) -> str | None:
    """Return the normalized current MAC, falling back to the permanent MAC."""
    return normalize_mac(adapter.current_mac_address) or normalize_mac(
        adapter.permanent_mac_address
    )


def _is_physical(adapter: Adapter) -> bool:
    return (
        adapter.is_physical
        and not adapter.is_virtual
        and adapter.adapter_type != "loopback"
    )


def _active_connected_physical(adapters: list[Adapter]) -> list[Adapter]:
    return [
        adapter
        for adapter in adapters
        if _is_physical(adapter)
        and adapter.is_active
        and adapter.is_connected
        and _mac_of(adapter) is not None
    ]


def select_preferred_adapter(adapters: list[Adapter]) -> Adapter | None:
    """Select the preferred-route owner, prioritizing physical adapters."""
    preferred_physical = [
        adapter
        for adapter in adapters
        if adapter.is_preferred and _is_physical(adapter)
    ]
    if preferred_physical:
        return preferred_physical[0]

    preferred = [
        adapter
        for adapter in adapters
        if adapter.is_preferred
        and adapter.adapter_type != "loopback"
    ]
    if preferred:
        return preferred[0]

    physical = _active_connected_physical(adapters)
    return physical[0] if physical else None


def select_primary_mac(adapters: list[Adapter]) -> str | None:
    """Select a normalized primary MAC without fabricating a value."""
    selected = select_preferred_adapter(adapters)
    if selected is None:
        return None

    selected_mac = _mac_of(selected)
    if selected_mac is None:
        return None

    if _is_physical(selected):
        return selected_mac

    physical_alternatives = _active_connected_physical(adapters)
    if physical_alternatives:
        return _mac_of(physical_alternatives[0])

    return selected_mac
