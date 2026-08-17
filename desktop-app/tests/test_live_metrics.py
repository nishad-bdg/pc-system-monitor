from system_info import live_metrics


class _Counters:
    def __init__(self, sent, recv):
        self.bytes_sent = sent
        self.bytes_recv = recv


class _VM:
    percent = 42.0
    used = 100
    total = 200


def test_collect_live_metrics_does_not_sleep(monkeypatch):
    live_metrics.reset_live_metrics_state()
    monkeypatch.setattr(live_metrics.psutil, "cpu_percent", lambda interval=None: 7.5)
    monkeypatch.setattr(live_metrics.psutil, "virtual_memory", lambda: _VM())
    monkeypatch.setattr(
        live_metrics.psutil, "net_io_counters", lambda: _Counters(1000, 2000)
    )

    def boom(*a, **k):
        raise AssertionError("live metrics must not sleep")

    monkeypatch.setattr(live_metrics.time, "sleep", boom)
    monkeypatch.setattr(
        "system_info.resources.cpu_identity",
        lambda: ("Intel", "Intel Core i5-10400"),
    )
    sample = live_metrics.collect_live_metrics()
    assert sample["cpu_percent"] == 7.5
    assert sample["cpu_name"] == "Intel Core i5-10400"
    assert sample["cpu_brand"] == "Intel"
    assert sample["ram_percent"] == 42.0
    assert sample["ram_used"] == 100
    assert sample["ram_total"] == 200
    assert sample["bytes_sent"] == 1000
    assert sample["bytes_recv"] == 2000
    assert sample["send_rate_bps"] == 0.0
    assert sample["recv_rate_bps"] == 0.0


def test_collect_live_metrics_rates_from_delta(monkeypatch):
    live_metrics.reset_live_metrics_state()
    clock = {"t": 10.0}
    monkeypatch.setattr(live_metrics.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(live_metrics.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(live_metrics.psutil, "virtual_memory", lambda: _VM())
    counters = [_Counters(1000, 2000), _Counters(2000, 4000)]
    monkeypatch.setattr(
        live_metrics.psutil, "net_io_counters", lambda: counters.pop(0)
    )
    monkeypatch.setattr("system_info.resources.cpu_identity", lambda: (None, None))

    first = live_metrics.collect_live_metrics()
    assert first["send_rate_bps"] == 0.0
    clock["t"] = 12.0
    second = live_metrics.collect_live_metrics()
    assert second["send_rate_bps"] == 500.0
    assert second["recv_rate_bps"] == 1000.0


def test_nic_kind_skips_virtual_and_ranks_ethernet():
    assert live_metrics.nic_kind("Ethernet") == "ethernet"
    assert live_metrics.nic_kind("Ethernet 2") == "ethernet"
    assert live_metrics.nic_kind("Realtek PCIe GbE Family Controller") == "ethernet"
    assert live_metrics.nic_kind("Wi-Fi") == "wifi"
    assert live_metrics.nic_kind("Loopback Pseudo-Interface 1") == "skip"
    assert live_metrics.nic_kind("vEthernet (WSL)") == "skip"
    assert live_metrics.nic_kind("lo") == "skip"


class _Stat:
    def __init__(self, isup=True, speed=1000):
        self.isup = isup
        self.speed = speed


def test_live_ethernet_prefers_up_ethernet_and_rates(monkeypatch):
    live_metrics.reset_live_metrics_state()
    clock = {"t": 10.0}
    monkeypatch.setattr(live_metrics.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(live_metrics.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(live_metrics.psutil, "virtual_memory", lambda: _VM())
    monkeypatch.setattr("system_info.resources.cpu_identity", lambda: (None, None))

    all_io = [_Counters(1000, 2000), _Counters(2000, 4000)]
    nics = [
        {
            "Loopback Pseudo-Interface 1": _Counters(9_000_000, 9_000_000),
            "Wi-Fi": _Counters(100, 200),
            "Ethernet": _Counters(1000, 2000),
        },
        {
            "Loopback Pseudo-Interface 1": _Counters(9_100_000, 9_100_000),
            "Wi-Fi": _Counters(10_000, 20_000),
            "Ethernet": _Counters(6000, 12000),
        },
    ]

    def fake_net_io(pernic=False):
        if pernic:
            return nics[0] if clock["t"] == 10.0 else nics[1]
        return all_io[0] if clock["t"] == 10.0 else all_io[1]

    monkeypatch.setattr(live_metrics.psutil, "net_io_counters", fake_net_io)
    monkeypatch.setattr(
        live_metrics.psutil,
        "net_if_stats",
        lambda: {
            "Ethernet": _Stat(True, 1000),
            "Wi-Fi": _Stat(True, 866),
            "Loopback Pseudo-Interface 1": _Stat(True, 1073),
        },
    )

    first = live_metrics.collect_live_metrics()
    assert first["eth_name"] == "Ethernet"
    assert first["eth_kind"] == "ethernet"
    assert first["eth_link_mbps"] == 1000
    assert first["eth_send_rate_bps"] == 0.0

    clock["t"] = 12.0
    second = live_metrics.collect_live_metrics()
    assert second["eth_name"] == "Ethernet"
    assert second["eth_send_rate_bps"] == 2500.0  # 5000 bytes / 2s
    assert second["eth_recv_rate_bps"] == 5000.0


def test_live_ethernet_skips_down_adapter(monkeypatch):
    live_metrics.reset_live_metrics_state()
    monkeypatch.setattr(live_metrics.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(live_metrics.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(live_metrics.psutil, "virtual_memory", lambda: _VM())
    monkeypatch.setattr("system_info.resources.cpu_identity", lambda: (None, None))

    def fake_net_io(pernic=False):
        if pernic:
            return {
                "Ethernet": _Counters(1_000_000, 2_000_000),
                "Wi-Fi": _Counters(100, 200),
            }
        return _Counters(100, 200)

    monkeypatch.setattr(live_metrics.psutil, "net_io_counters", fake_net_io)
    monkeypatch.setattr(
        live_metrics.psutil,
        "net_if_stats",
        lambda: {
            "Ethernet": _Stat(False, 1000),
            "Wi-Fi": _Stat(True, 400),
        },
    )
    sample = live_metrics.collect_live_metrics()
    assert sample["eth_name"] == "Wi-Fi"
    assert sample["eth_kind"] == "wifi"
    assert sample["eth_link_mbps"] == 400
