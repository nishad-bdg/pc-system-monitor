"""Network bandwidth totals, rates, and approximate internet download speed."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil
import requests

_RATE_INTERVAL = 0.5
_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=1000000"
_DOWNLOAD_TIMEOUT = 8.0
_DOWNLOAD_BYTES = 1_000_000


@dataclass
class NetworkUsage:
    bytes_sent: int
    bytes_recv: int
    send_rate_bps: float
    recv_rate_bps: float
    download_mbps: float | None = None
    upload_mbps: float | None = None

    def to_dict(self) -> dict:
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "send_rate_bps": self.send_rate_bps,
            "recv_rate_bps": self.recv_rate_bps,
            "download_mbps": self.download_mbps,
            "upload_mbps": self.upload_mbps,
        }


def measure_download_mbps(
    url: str = _DOWNLOAD_URL,
    timeout: float = _DOWNLOAD_TIMEOUT,
) -> float | None:
    """Timed HTTPS download of a small object → approximate Mbps. Fail soft."""
    try:
        started = time.monotonic()
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    total += len(chunk)
        elapsed = time.monotonic() - started
        if elapsed <= 0 or total <= 0:
            return None
        return (total * 8) / (elapsed * 1_000_000)
    except (requests.RequestException, OSError, ValueError):
        return None


def collect_network_usage(
    interval: float = _RATE_INTERVAL,
    *,
    probe_download: bool = True,
) -> NetworkUsage:
    """Totals since boot, short-interval NIC rates, optional download Mbps."""
    first = psutil.net_io_counters()
    time.sleep(max(0.1, interval))
    second = psutil.net_io_counters()
    dt = max(interval, 0.1)
    download_mbps = measure_download_mbps() if probe_download else None
    return NetworkUsage(
        bytes_sent=int(second.bytes_sent),
        bytes_recv=int(second.bytes_recv),
        send_rate_bps=max(0.0, (second.bytes_sent - first.bytes_sent) / dt),
        recv_rate_bps=max(0.0, (second.bytes_recv - first.bytes_recv) / dt),
        download_mbps=download_mbps,
        upload_mbps=None,
    )
