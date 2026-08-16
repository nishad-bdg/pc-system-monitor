"""Lightweight CPU / RAM / network samples for live dashboard gauges.

Unlike `collect_resources` / `collect_network_usage` this never sleeps for a
peak window, never runs WMI/`system_profiler`, and is safe to call every few
seconds from the watcher.
"""

from __future__ import annotations

import time

import psutil

_cpu_primed = False
_last_net: tuple[float, int, int] | None = None  # monotonic ts, sent, recv


def reset_live_metrics_state() -> None:
    """Clear CPU/network baselines (tests)."""
    global _cpu_primed, _last_net
    _cpu_primed = False
    _last_net = None


def collect_live_metrics() -> dict:
    """Instant CPU %, RAM, NIC totals, and rate since the previous call.

    The first call primes psutil and returns 0 for CPU and network rates.
    Later calls return the average since then (the watcher's 5s cadence).
    """
    global _cpu_primed, _last_net

    if not _cpu_primed:
        psutil.cpu_percent(interval=None)
        _cpu_primed = True
    cpu_percent = float(psutil.cpu_percent(interval=None))

    vm = psutil.virtual_memory()
    io = psutil.net_io_counters()
    now = time.monotonic()
    sent = int(getattr(io, "bytes_sent", 0) or 0)
    recv = int(getattr(io, "bytes_recv", 0) or 0)
    send_rate = 0.0
    recv_rate = 0.0
    if _last_net is not None:
        prev_ts, prev_sent, prev_recv = _last_net
        dt = max(now - prev_ts, 0.001)
        send_rate = max(0.0, (sent - prev_sent) / dt)
        recv_rate = max(0.0, (recv - prev_recv) / dt)
    _last_net = (now, sent, recv)

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": float(vm.percent),
        "ram_used": int(vm.used),
        "ram_total": int(vm.total),
        "bytes_sent": sent,
        "bytes_recv": recv,
        "send_rate_bps": send_rate,
        "recv_rate_bps": recv_rate,
    }
