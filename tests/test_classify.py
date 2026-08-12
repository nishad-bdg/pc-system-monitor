from desktop_monitoring.network.classify import (
    infer_adapter_type,
    is_loopback,
    is_virtual_adapter,
)


def test_loopback_excluded_from_physical():
    assert is_loopback("Loopback Pseudo-Interface 1", "Software Loopback")
    assert is_loopback("lo", None)


def test_virtual_keywords():
    assert is_virtual_adapter("vEthernet (Default Switch)", "Hyper-V Virtual Ethernet Adapter")
    assert is_virtual_adapter("DockerNAT", "Docker")
    assert is_virtual_adapter("WSL", "WSL")
    assert is_virtual_adapter("VMware Network Adapter VMnet8", "VMware")
    assert is_virtual_adapter("VirtualBox Host-Only", "VirtualBox")
    assert is_virtual_adapter("NordLynx", "VPN", adapter_type="vpn")
    assert is_virtual_adapter("Bluetooth Network Connection", "Bluetooth")


def test_physical_wifi_and_ethernet():
    assert not is_virtual_adapter("Wi-Fi", "Intel(R) Wi-Fi 6 AX201 160MHz")
    assert not is_virtual_adapter("Ethernet", "Intel(R) Ethernet Connection")
    assert infer_adapter_type("Wi-Fi", "Intel Wi-Fi", "802.11") == "wifi"
    assert infer_adapter_type("Ethernet", "Intel Ethernet", "802.3") == "ethernet"
