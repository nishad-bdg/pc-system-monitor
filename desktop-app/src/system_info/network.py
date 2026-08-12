"""Network bandwidth totals and rates (psutil)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil

_RATE_INTERVAL = 0.5


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


def collect_network_usage(interval: float = _RATE_INTERVAL) -> NetworkUsage:
    """Totals since boot plus a short-interval send/recv rate."""
    first = psutil.net_io_counters()
    time.sleep(max(0.1, interval))
    second = psutil.net_io_counters()
    dt = max(interval, 0.1)
    return NetworkUsage(
        bytes_sent=int(second.bytes_sent),
        bytes_recv=int(second.bytes_recv),
        send_rate_bps=max(0.0, (second.bytes_sent - first.bytes_sent) / dt),
        recv_rate_bps=max(0.0, (second.bytes_recv - first.bytes_recv) / dt),
    )
