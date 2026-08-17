"""Top processes by CPU, RAM, and open network connections.

Live path (`interval=None`) never sleeps: `cpu_percent(interval=None)` is
primed on the first call and returns usage since the previous sample on later
calls (the watcher's 5s cadence). One-shot collect may pass a short interval
so the first snapshot is not all zeros.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import psutil

TOP_N = 10
CPU_SAMPLE_INTERVAL = 0.3
_SKIP_NAMES = frozenset({
    "",
    "idle",
    "system idle process",
    "kernel_task",
})


@dataclass
class ProcessRow:
    pid: int
    name: str
    username: str | None
    cpu_percent: float
    memory_rss: int
    memory_percent: float
    connections: int

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "name": self.name,
            "username": self.username,
            "cpu_percent": self.cpu_percent,
            "memory_rss": self.memory_rss,
            "memory_percent": round(self.memory_percent, 2),
            "connections": self.connections,
        }


@dataclass
class TopProcesses:
    cpu: list[ProcessRow] = field(default_factory=list)
    ram: list[ProcessRow] = field(default_factory=list)
    network: list[ProcessRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cpu": [p.to_dict() for p in self.cpu],
            "ram": [p.to_dict() for p in self.ram],
            "network": [p.to_dict() for p in self.network],
        }


def _connection_counts() -> dict[int, int]:
    """One system-wide inet connection list, grouped by pid.

    Per-process bytes/sec is not available without packet capture, so
    connection count is the live network ranking.
    """
    counts: dict[int, int] = {}
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.Error, OSError):
        return counts
    for conn in conns:
        pid = getattr(conn, "pid", None)
        if not pid:
            continue
        counts[pid] = counts.get(pid, 0) + 1
    return counts


def _safe_username(proc: psutil.Process) -> str | None:
    try:
        name = proc.username()
    except (psutil.Error, OSError):
        return None
    text = str(name or "").strip()
    return text or None


def collect_top_processes(
    top_n: int = TOP_N,
    interval: float | None = None,
) -> TopProcesses:
    """Busiest processes. `interval=None` is non-blocking (live WS samples)."""
    ncpu = float(psutil.cpu_count(logical=True) or 1)
    conns = _connection_counts()

    if interval is not None:
        for proc in psutil.process_iter(["pid"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.Error, OSError):
                continue
        time.sleep(max(0.05, interval))

    rows: list[ProcessRow] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            with proc.oneshot():
                name = str(proc.name() or "").strip()
                if name.lower() in _SKIP_NAMES:
                    continue
                pid = int(proc.pid)
                if pid <= 0:
                    continue
                cpu_raw = float(proc.cpu_percent(interval=None) or 0.0)
                mem = proc.memory_info()
                rss = int(getattr(mem, "rss", 0) or 0)
                mem_pct = float(proc.memory_percent() or 0.0)
        except (psutil.Error, OSError, TypeError, ValueError):
            continue
        rows.append(
            ProcessRow(
                pid=pid,
                name=name or f"pid-{pid}",
                username=_safe_username(proc),
                cpu_percent=round(cpu_raw / ncpu, 2),
                memory_rss=rss,
                memory_percent=mem_pct,
                connections=int(conns.get(pid, 0)),
            )
        )

    cpu = sorted(rows, key=lambda p: p.cpu_percent, reverse=True)[:top_n]
    ram = sorted(rows, key=lambda p: p.memory_rss, reverse=True)[:top_n]
    networked = [p for p in rows if p.connections > 0]
    network = sorted(networked, key=lambda p: p.connections, reverse=True)[:top_n]
    return TopProcesses(cpu=cpu, ram=ram, network=network)
