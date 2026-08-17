import contextlib

from system_info import processes


class _Mem:
    def __init__(self, rss):
        self.rss = rss


class _FakeProc:
    def __init__(self, pid, name, cpu, rss, mem_pct, username="user"):
        self.pid = pid
        self._name = name
        self._cpu = cpu
        self._rss = rss
        self._mem_pct = mem_pct
        self._username = username

    def oneshot(self):
        return contextlib.nullcontext()

    def cpu_percent(self, interval=None):
        return self._cpu

    def name(self):
        return self._name

    def memory_info(self):
        return _Mem(self._rss)

    def memory_percent(self):
        return self._mem_pct

    def username(self):
        return self._username


def test_collect_top_processes_live_does_not_sleep(monkeypatch):
    procs = [
        _FakeProc(11, "chrome", 80.0, 200, 10.0),
        _FakeProc(12, "code", 20.0, 400, 20.0),
        _FakeProc(13, "Idle", 5.0, 10, 0.1),
    ]
    monkeypatch.setattr(processes.psutil, "cpu_count", lambda logical=True: 4)
    monkeypatch.setattr(processes.psutil, "process_iter", lambda attrs=None: procs)
    monkeypatch.setattr(
        processes.psutil,
        "net_connections",
        lambda kind="inet": [
            type("C", (), {"pid": 11})(),
            type("C", (), {"pid": 11})(),
            type("C", (), {"pid": 12})(),
        ],
    )

    def boom(*a, **k):
        raise AssertionError("live process collect must not sleep")

    monkeypatch.setattr(processes.time, "sleep", boom)
    tops = processes.collect_top_processes(interval=None)
    names_cpu = [p.name for p in tops.cpu]
    assert names_cpu[0] == "chrome"
    assert "Idle" not in names_cpu
    assert tops.ram[0].name == "code"
    assert tops.network[0].name == "chrome"
    assert tops.network[0].connections == 2
    payload = tops.to_dict()
    assert set(payload) == {"cpu", "ram", "network"}
    assert payload["cpu"][0]["cpu_percent"] == 20.0  # 80 / 4 cores


def test_collect_top_processes_interval_sleeps(monkeypatch):
    slept = {"n": 0}
    monkeypatch.setattr(processes.psutil, "cpu_count", lambda logical=True: 1)
    monkeypatch.setattr(processes.psutil, "process_iter", lambda attrs=None: [])
    monkeypatch.setattr(processes.psutil, "net_connections", lambda kind="inet": [])
    monkeypatch.setattr(processes.time, "sleep", lambda s: slept.update(n=slept["n"] + 1))
    processes.collect_top_processes(interval=0.15)
    assert slept["n"] == 1
