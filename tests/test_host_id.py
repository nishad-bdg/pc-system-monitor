from desktop_monitoring.host_id import build_host_id


def test_host_id_not_equal_to_mac_alone():
    mac = "AA:BB:CC:DD:EE:FF"
    host_id = build_host_id(
        hostname="DESKTOP-1",
        machine_guid="GUID-1",
        primary_mac=mac,
    )
    assert host_id != mac
    assert host_id == "DESKTOP-1|GUID-1"


def test_host_id_stable_without_mac():
    without_mac = build_host_id("DESKTOP-1", "GUID-1", None)
    with_mac = build_host_id(
        "DESKTOP-1",
        "GUID-1",
        "AA:BB:CC:DD:EE:FF",
    )
    assert without_mac == with_mac


def test_host_id_uses_non_mac_fallbacks_for_missing_anchors():
    assert build_host_id("", None, "AA:BB:CC:DD:EE:FF") == (
        "unknown-host|unknown-guid"
    )
