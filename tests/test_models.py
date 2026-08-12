from desktop_monitoring.network.models import Adapter, adapter_to_dict


def test_adapter_to_dict_includes_mac_fields_and_laa_flag():
    adapter = Adapter(
        name="Wi-Fi",
        current_mac_address="02aabbccddee",
        permanent_mac_address="aa:bb:cc:dd:ee:ff",
        is_physical=True,
    )
    payload = adapter_to_dict(adapter)
    assert payload["current_mac_address"] == "02:AA:BB:CC:DD:EE"
    assert payload["permanent_mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert payload["is_randomized_or_locally_administered"] is True
