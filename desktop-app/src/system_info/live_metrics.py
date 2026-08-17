"""Lightweight CPU / RAM / network samples for live dashboard gauges.

Unlike `collect_resources` / `collect_network_usage` this never sleeps for a
peak window. CPU name/brand are read once and cached (Windows registry, not
every 5s). Ethernet send/receive is the busiest physical NIC since the last
sample (Task Manager style). Safe to call every few seconds from the watcher.
"""

from __future__ import annotations

import re
import time

import psutil

_cpu_primed = False
_last_net: tuple[float, int, int] | None = None  # monotonic ts, sent, recv
_last_nics: dict[str, tuple[int, int]] = {}  # name -> sent, recv at last sample
_last_nic_ts: float | None = None

_SKIP_NIC = re.compile(
    r"loopback|isatap|teredo|6to4|bluetooth|vmware|vbox|virtualbox|"
    r"hyper-v|vethernet|docker|wsl|br-|veth|tun|tap|utun|awdl|llw|"
    r"dummy|virbr|kube|cni|npcap|pseudo",
    re.IGNORECASE,
)
_WIFI_NIC = re.compile(r"wi-?fi|wlan|wireless|airport|\bwl", re.IGNORECASE)
_ETHER_NIC = re.compile(
    r"ethernet|\beth\d|\ben\d|realtek|i225|i226|e1000|igb|igc|nic",
    re.IGNORECASE,
)


def reset_live_metrics_state() -> None:
    """Clear CPU/network baselines (tests)."""
    global _cpu_primed, _last_net, _last_nics, _last_nic_ts
    _cpu_primed = False
    _last_net = None
    _last_nics = {}
    _last_nic_ts = None
    try:
        from .resources import reset_cpu_identity_cache

        reset_cpu_identity_cache()
    except Exception:
        pass


def nic_kind(name: str) -> str:
    """ethernet | wifi | other | skip — used to pick a Task Manager-style NIC."""
    text = str(name or "").strip()
    lower = text.lower()
    if lower in {"lo", "lo0"} or _SKIP_NIC.search(lower):
        return "skip"
    if _WIFI_NIC.search(lower):
        return "wifi"
    if _ETHER_NIC.search(lower) or lower.startswith("eth"):
        return "ethernet"
    return "other"


def _kind_rank(kind: str) -> int:
    return {"ethernet": 0, "other": 1, "wifi": 2}.get(kind, 9)


def _live_ethernet(now: float) -> dict:
    """Send/receive on the preferred physical NIC since the last sample."""
    global _last_nics, _last_nic_ts
    try:
        pernic = psutil.net_io_counters(pernic=True)
    except (OSError, AttributeError, TypeError):
        return {}
    if not isinstance(pernic, dict):
        return {}
    try:
        stats = psutil.net_if_stats()
    except (OSError, AttributeError, TypeError):
        stats = {}

    dt = max((now - _last_nic_ts) if _last_nic_ts is not None else 0.0, 0.001)
    candidates: list[tuple] = []
    snapshot: dict[str, tuple[int, int]] = {}
    for name, io in pernic.items():
        kind = nic_kind(str(name))
        if kind == "skip":
            continue
        st = stats.get(name) if isinstance(stats, dict) else None
        if st is not None and hasattr(st, "isup") and not st.isup:
            continue
        sent = int(getattr(io, "bytes_sent", 0) or 0)
        recv = int(getattr(io, "bytes_recv", 0) or 0)
        snapshot[str(name)] = (sent, recv)
        prev = _last_nics.get(str(name))
        send_rate = 0.0
        recv_rate = 0.0
        if prev is not None and _last_nic_ts is not None:
            send_rate = max(0.0, (sent - prev[0]) / dt)
            recv_rate = max(0.0, (recv - prev[1]) / dt)
        link = None
        try:
            if st is not None and int(getattr(st, "speed", 0) or 0) > 0:
                link = int(st.speed)
        except (TypeError, ValueError):
            link = None
        candidates.append(
            (_kind_rank(kind), -(send_rate + recv_rate), -(sent + recv), str(name), send_rate, recv_rate, link, kind)
        )

    _last_nics = snapshot
    _last_nic_ts = now
    if not candidates:
        return {}
    candidates.sort()
    _rank, _nr, _nb, name, send_rate, recv_rate, link, kind = candidates[0]
    out = {
        "eth_name": name[:80],
        "eth_kind": kind,
        "eth_send_rate_bps": send_rate,
        "eth_recv_rate_bps": recv_rate,
    }
    if link:
        out["eth_link_mbps"] = link
    return out


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

    cpu_brand = None
    cpu_name = None
    try:
        from .resources import cpu_identity

        cpu_brand, cpu_name = cpu_identity()
    except Exception:
        pass

    sample = {
        "cpu_percent": cpu_percent,
        "ram_percent": float(vm.percent),
        "ram_used": int(vm.used),
        "ram_total": int(vm.total),
        "bytes_sent": sent,
        "bytes_recv": recv,
        "send_rate_bps": send_rate,
        "recv_rate_bps": recv_rate,
    }
    if cpu_name:
        sample["cpu_name"] = cpu_name
    if cpu_brand:
        sample["cpu_brand"] = cpu_brand
    sample.update(_live_ethernet(now))
    return sample
