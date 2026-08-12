from desktop_monitoring.network.models import Adapter
from desktop_monitoring.snapshot import build_snapshot


def test_snapshot_json_always_has_mac_contract_fields():
    adapters = [
        Adapter(
            name="Wi-Fi",
            description="Intel Wi-Fi",
            interface_index=12,
            adapter_type="wifi",
            is_physical=True,
            is_virtual=False,
            is_active=True,
            is_connected=True,
            is_preferred=True,
            current_mac_address="AA:BB:CC:DD:EE:FF",
            permanent_mac_address="AA:BB:CC:DD:EE:FF",
            ipv4_addresses=["192.168.1.25"],
        )
    ]
    snapshot = build_snapshot(
        hostname="DESKTOP-1",
        machine_guid="GUID-1",
        adapters=adapters,
    )
    network = snapshot["network"]
    assert "primary_mac_address" in network
    assert "current_mac_address" in network["preferred_adapter"]
    assert "permanent_mac_address" in network["preferred_adapter"]
    for item in network["active_adapters"] + network["all_adapters"]:
        assert "current_mac_address" in item
        assert "permanent_mac_address" in item
    assert snapshot["host_id"] != network["primary_mac_address"]


def test_empty_snapshot_still_has_mac_contract_fields():
    snapshot = build_snapshot(
        hostname="DESKTOP-1",
        machine_guid="GUID-1",
        adapters=[],
    )
    network = snapshot["network"]
    assert network["primary_mac_address"] is None
    assert network["preferred_adapter"]["current_mac_address"] is None
    assert network["preferred_adapter"]["permanent_mac_address"] is None


def test_supplied_network_is_completed_without_mutating_source():
    source = {
        "preferred_adapter": {"name": "Wi-Fi"},
        "active_adapters": [{"name": "Wi-Fi"}],
        "all_adapters": [{"name": "Wi-Fi"}],
    }

    snapshot = build_snapshot("DESKTOP-1", "GUID-1", network=source)
    network = snapshot["network"]

    assert network["primary_mac_address"] is None
    assert network["preferred_adapter"]["current_mac_address"] is None
    assert network["preferred_adapter"]["permanent_mac_address"] is None
    assert network["active_adapters"][0]["current_mac_address"] is None
    assert network["active_adapters"][0]["permanent_mac_address"] is None
    assert network["all_adapters"][0]["current_mac_address"] is None
    assert network["all_adapters"][0]["permanent_mac_address"] is None
    assert "primary_mac_address" not in source
