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
    sample = live_metrics.collect_live_metrics()
    assert sample["cpu_percent"] == 7.5
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

    first = live_metrics.collect_live_metrics()
    assert first["send_rate_bps"] == 0.0
    clock["t"] = 12.0
    second = live_metrics.collect_live_metrics()
    assert second["send_rate_bps"] == 500.0
    assert second["recv_rate_bps"] == 1000.0
