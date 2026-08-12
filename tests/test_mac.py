import pytest

from desktop_monitoring.network.mac import (
    is_randomized_or_locally_administered,
    normalize_mac,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF"),
        ("AABBCCDDEEFF", "AA:BB:CC:DD:EE:FF"),
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF"),
        (None, None),
        ("", None),
        ("   ", None),
        ("00:00:00:00:00:00", None),
        ("FF:FF:FF:FF:FF:FF", None),
        ("not-a-mac", None),
        ("AA:BB:CC:DD:EE", None),
        ("GG:BB:CC:DD:EE:FF", None),
    ],
)
def test_normalize_mac(raw, expected):
    assert normalize_mac(raw) == expected


@pytest.mark.parametrize(
    "mac, expected",
    [
        ("02:11:22:33:44:55", True),   # locally administered bit set
        ("06:11:22:33:44:55", True),
        ("0A:11:22:33:44:55", True),
        ("0E:11:22:33:44:55", True),
        ("00:11:22:33:44:55", False),
        ("AA:BB:CC:DD:EE:FF", True),   # U/L bit set on first octet 0xAA
        (None, False),
        ("not-a-mac", False),
    ],
)
def test_is_randomized_or_locally_administered(mac, expected):
    assert is_randomized_or_locally_administered(mac) is expected
