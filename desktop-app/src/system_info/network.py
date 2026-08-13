"""Network bandwidth totals and rates (psutil)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil

_RATE_INTERVAL = 0.5
_WINDOW_SECONDS = 3.0


@dataclass
class NetworkUsage:
    bytes_sent: int
    bytes_recv: int
    send_rate_bps: float
    recv_rate_bps: float

    def to_dict(self) -> dict:
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "send_rate_bps": self.send_rate_bps,
            "recv_rate_bps": self.recv_rate_bps,
        }


def collect_network_usage(interval: float = _RATE_INTERVAL, window: float = _WINDOW_SECONDS) -> NetworkUsage:
    """Totals since boot plus a send/recv rate.

    The rate is the *peak* short-interval sample observed over a ~3 second
    window, so a momentary burst (e.g. a speed test or download) is captured
    instead of a single 0.5s point-sample that can catch an idle moment.
    """
    first = psutil.net_io_counters()
    sleep_step = max(0.1, min(interval, window))
    dt = max(sleep_step, 0.1)
    peak_sent = 0.0
    peak_recv = 0.0
    prev = first
    elapsed = 0.0
    while elapsed < window:
        time.sleep(sleep_step)
        elapsed += dt
        curr = psutil.net_io_counters()
        peak_sent = max(peak_sent, (curr.bytes_sent - prev.bytes_sent) / dt)
        peak_recv = max(peak_recv, (curr.bytes_recv - prev.bytes_recv) / dt)
        prev = curr
    final = psutil.net_io_counters()
    return NetworkUsage(
        bytes_sent=int(final.bytes_sent),
        bytes_recv=int(final.bytes_recv),
        send_rate_bps=max(0.0, peak_sent),
        recv_rate_bps=max(0.0, peak_recv),
    )
