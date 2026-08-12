import json
from pathlib import Path

from desktop_monitoring.network.collector import (
    _map_powershell_adapter,
    build_network_payload,
    collect_network,
)
from desktop_monitoring.network.mac import is_randomized_or_locally_administered
from desktop_monitoring.network.models import Adapter


def _load(fixtures_dir: Path, name: str) -> list[Adapter]:
    return [Adapter(**row) for row in json.loads((fixtures_dir / name).read_text())]


def test_build_network_includes_required_mac_fields(fixtures_dir: Path):
    adapters = _load(fixtures_dir, "adapters_physical_wifi.json")
    network = build_network_payload(adapters)

    assert network["primary_mac_address"] == "AA:BB:CC:DD:EE:FF"
    preferred = network["preferred_adapter"]
    assert preferred["current_mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert preferred["permanent_mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert "is_randomized_or_locally_administered" in preferred
    for bucket in ("active_adapters", "all_adapters"):
        assert network[bucket]
        for item in network[bucket]:
            assert "current_mac_address" in item
            assert "permanent_mac_address" in item
            assert "is_randomized_or_locally_administered" in item


def test_physical_adapter_count_excludes_loopback(fixtures_dir: Path):
    adapters = _load(fixtures_dir, "adapters_physical_wifi.json")
    network = build_network_payload(adapters)

    assert network["physical_adapter_count"] == 1
    assert network["active_adapter_count"] == 2


def test_randomized_wifi_keeps_both_macs(fixtures_dir: Path):
    adapters = _load(fixtures_dir, "adapters_randomized_wifi.json")
    network = build_network_payload(adapters)

    preferred = network["preferred_adapter"]
    assert preferred["current_mac_address"] == "02:11:22:33:44:55"
    assert preferred["permanent_mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert preferred["is_randomized_or_locally_administered"] is True
    assert is_randomized_or_locally_administered(preferred["current_mac_address"])


def test_virtual_not_primary_when_physical_preferred_exists():
    adapters = [
        Adapter(
            name="Wi-Fi",
            description="Intel Wi-Fi",
            adapter_type="wifi",
            is_physical=True,
            is_virtual=False,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="AA:BB:CC:DD:EE:FF",
            permanent_mac_address="AA:BB:CC:DD:EE:FF",
            ipv4_addresses=["192.168.1.25"],
        ),
        Adapter(
            name="vEthernet (Default Switch)",
            description="Hyper-V Virtual Ethernet Adapter",
            adapter_type="virtual",
            is_physical=False,
            is_virtual=True,
            is_active=True,
            is_connected=True,
            is_preferred=False,
            current_mac_address="00:15:5D:AA:BB:CC",
            permanent_mac_address="00:15:5D:AA:BB:CC",
        ),
    ]

    network = build_network_payload(adapters)

    assert network["primary_mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert network["preferred_adapter"]["name"] == "Wi-Fi"
    assert any(a["name"].startswith("vEthernet") for a in network["all_adapters"])


def test_invalid_mac_becomes_null_in_payload():
    adapters = [
        Adapter(
            name="Wi-Fi",
            is_physical=True,
            is_virtual=False,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="not-a-mac",
            permanent_mac_address="GG:HH:II:JJ:KK:LL",
            ipv4_addresses=["10.0.0.2"],
        )
    ]

    network = build_network_payload(adapters)

    assert network["primary_mac_address"] is None
    assert network["preferred_adapter"]["current_mac_address"] is None
    assert network["preferred_adapter"]["permanent_mac_address"] is None


def test_missing_permanent_mac_is_not_fabricated_from_current_mac():
    adapter = _map_powershell_adapter(
        {
            "Name": "Wi-Fi",
            "InterfaceDescription": "Intel Wi-Fi",
            "ifIndex": 12,
            "Status": "Up",
            "MacAddress": "AA-BB-CC-DD-EE-FF",
            "PermanentAddress": None,
        },
        preferred_index=12,
    )

    assert adapter.current_mac_address == "AA:BB:CC:DD:EE:FF"
    assert adapter.permanent_mac_address is None


def test_map_powershell_adapter_treats_non_hardware_interface_as_virtual():
    adapter = _map_powershell_adapter(
        {
            "Name": "WAN Miniport (IKEv2)",
            "InterfaceDescription": "WAN Miniport (IKEv2)",
            "ifIndex": 31,
            "Status": "Up",
            "HardwareInterface": False,
            "MacAddress": "02-11-22-33-44-55",
        },
        preferred_index=31,
    )

    assert adapter.is_virtual is True
    assert adapter.is_physical is False


def test_collect_network_keeps_adapters_when_route_lookup_fails(monkeypatch):
    from desktop_monitoring.network import powershell

    def fail_route_lookup():
        raise powershell.PowerShellError("route lookup failed")

    monkeypatch.setattr(
        powershell,
        "fetch_default_route_interface_index",
        fail_route_lookup,
    )
    monkeypatch.setattr(
        powershell,
        "fetch_net_adapters",
        lambda: [
            {
                "Name": "Ethernet",
                "InterfaceDescription": "Intel Ethernet",
                "ifIndex": 7,
                "Status": "Up",
                "HardwareInterface": True,
                "MacAddress": "AA-BB-CC-DD-EE-FF",
                "PermanentAddress": "AA-BB-CC-DD-EE-FF",
            }
        ],
    )
    monkeypatch.setattr(powershell, "fetch_net_ip_configuration", lambda: [])

    network = collect_network()

    assert len(network["all_adapters"]) == 1
    assert network["all_adapters"][0]["name"] == "Ethernet"
    assert network["all_adapters"][0]["is_preferred"] is False
    assert network["primary_mac_address"] == "AA:BB:CC:DD:EE:FF"
