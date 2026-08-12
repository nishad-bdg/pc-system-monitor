import json
from pathlib import Path

from desktop_monitoring.network.models import Adapter
from desktop_monitoring.network.select import (
    select_preferred_adapter,
    select_primary_mac,
)


def _load(fixtures_dir: Path, name: str) -> list[Adapter]:
    raw = json.loads((fixtures_dir / name).read_text())
    return [Adapter(**item) for item in raw]


def test_preferred_physical_wifi_mac(fixtures_dir: Path):
    adapters = _load(fixtures_dir, "adapters_physical_wifi.json")

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "Wi-Fi"
    assert select_primary_mac(adapters) == "AA:BB:CC:DD:EE:FF"


def test_loopback_not_selected_as_primary(fixtures_dir: Path):
    adapters = _load(fixtures_dir, "adapters_physical_wifi.json")

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.adapter_type != "loopback"
    assert select_primary_mac(adapters) is not None


def test_virtual_preferred_used_when_no_physical_alternative_is_available(
    fixtures_dir: Path,
):
    adapters = _load(fixtures_dir, "adapters_virtual_preferred.json")

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "vEthernet (WSL)"
    assert select_primary_mac(adapters) == "00:15:5D:01:02:03"


def test_physical_preferred_beats_virtual_preferred():
    adapters = [
        Adapter(
            name="Wi-Fi",
            adapter_type="wifi",
            is_physical=True,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="aa-bb-cc-dd-ee-ff",
        ),
        Adapter(
            name="vEthernet (Default Switch)",
            adapter_type="virtual",
            is_virtual=True,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="00:15:5D:AA:BB:CC",
        ),
    ]

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "Wi-Fi"
    assert select_primary_mac(adapters) == "AA:BB:CC:DD:EE:FF"


def test_physical_preferred_without_mac_blocks_virtual_preferred_mac():
    adapters = [
        Adapter(
            name="Wi-Fi",
            adapter_type="wifi",
            is_physical=True,
            is_active=True,
            is_connected=True,
            is_preferred=True,
        ),
        Adapter(
            name="vEthernet (Default Switch)",
            adapter_type="virtual",
            is_virtual=True,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="00:15:5D:AA:BB:CC",
        ),
    ]

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "Wi-Fi"
    assert select_primary_mac(adapters) is None


def test_connected_physical_mac_prevents_virtual_primary_selection():
    adapters = [
        Adapter(
            name="Ethernet",
            adapter_type="ethernet",
            is_physical=True,
            is_active=True,
            is_connected=True,
            current_mac_address="11-22-33-44-55-66",
        ),
        Adapter(
            name="VPN",
            adapter_type="vpn",
            is_virtual=True,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="02:15:5d:01:02:03",
        ),
    ]

    assert select_primary_mac(adapters) == "11:22:33:44:55:66"


def test_ethernet_and_wifi_prefer_marked_preferred():
    adapters = [
        Adapter(
            name="Ethernet",
            adapter_type="ethernet",
            is_physical=True,
            is_connected=True,
            is_active=True,
            current_mac_address="11:22:33:44:55:66",
        ),
        Adapter(
            name="Wi-Fi",
            adapter_type="wifi",
            is_physical=True,
            is_connected=True,
            is_active=True,
            is_preferred=True,
            current_mac_address="AA:BB:CC:DD:EE:FF",
        ),
    ]

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "Wi-Fi"
    assert select_primary_mac(adapters) == "AA:BB:CC:DD:EE:FF"


def test_randomized_current_still_selected_with_distinct_permanent(
    fixtures_dir: Path,
):
    adapters = _load(fixtures_dir, "adapters_randomized_wifi.json")

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.current_mac_address == "02:11:22:33:44:55"
    assert preferred.permanent_mac_address == "AA:BB:CC:DD:EE:FF"
    assert select_primary_mac(adapters) == "02:11:22:33:44:55"


def test_invalid_current_mac_falls_back_to_normalized_permanent_mac():
    adapters = [
        Adapter(
            name="Wi-Fi",
            is_physical=True,
            is_preferred=True,
            is_connected=True,
            is_active=True,
            current_mac_address="not-a-mac",
            permanent_mac_address="aabb.ccdd.eeff",
        )
    ]

    assert select_primary_mac(adapters) == "AA:BB:CC:DD:EE:FF"


def test_missing_mac_returns_none():
    adapters = [
        Adapter(
            name="Wi-Fi",
            is_physical=True,
            is_preferred=True,
            is_connected=True,
            is_active=True,
        )
    ]

    preferred = select_preferred_adapter(adapters)

    assert preferred is not None
    assert preferred.name == "Wi-Fi"
    assert select_primary_mac(adapters) is None
