"""In-process WebSocket broadcaster + presence cache.

Holds the set of connected admin clients and lets handlers push
`report.created` / `presence.changed` / `print.job` / `metrics.sample`
events to every open socket. Because the app may run multiple uvicorn
workers, this is best-effort per-process; the dashboard also refetches on
reconnect, so no event is permanently lost in practice.

The presence cache mirrors the `machines` collection in memory so that:
  - a connected `/ws/agent` socket (or heartbeat) flips a dot to green instantly, and
  - a freshly-connected dashboard receives the current online/offline map.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Set

from starlette.websockets import WebSocket

_clients: Set[WebSocket] = set()

# device_id -> {"online": bool, "last_seen": float, "pc_name": str | None}
_presence: dict[str, dict] = {}

# device_id -> list of connected desktop-agent sockets (API-key authed /ws/agent).
# Commands (restart/shutdown) are pushed to these instantly.
_agent_clients: dict[str, list[WebSocket]] = {}

# ping_id -> Future resolved when the agent replies with pong.
_pending_pings: dict[str, asyncio.Future] = {}


def connect_agent(device_id: str, ws: WebSocket) -> None:
    """Register a connected desktop agent socket for immediate command push."""
    sockets = _agent_clients.setdefault(device_id, [])
    if ws not in sockets:
        sockets.append(ws)


def disconnect_agent(device_id: str, ws: WebSocket) -> int:
    """Drop a desktop agent socket on disconnect/close.

    Returns the number of remaining sockets for this device (0 = last one).
    """
    sockets = _agent_clients.get(device_id)
    if not sockets:
        return 0
    try:
        sockets.remove(ws)
    except ValueError:
        pass
    if not sockets:
        _agent_clients.pop(device_id, None)
        return 0
    return len(sockets)


def agent_sockets(device_id: str) -> list[WebSocket]:
    """All currently-connected agent sockets for a device (best-effort)."""
    return list(_agent_clients.get(device_id) or [])


def connected_agent_device_ids() -> list[str]:
    """Every device_id with at least one live desktop-agent socket."""
    return [dev for dev, sockets in _agent_clients.items() if sockets]


def resolve_pong(ping_id: str) -> None:
    """Unblock a waiting admin ping when the agent replies."""
    fut = _pending_pings.get((ping_id or "").strip())
    if fut is not None and not fut.done():
        fut.set_result(True)


async def ping_agent(device_id: str, timeout: float = 3.0) -> dict:
    """Probe a live agent socket. Returns connected + round-trip ms."""
    device_id = (device_id or "").strip()
    sockets = agent_sockets(device_id)
    if not device_id or not sockets:
        return {"connected": False, "rtt_ms": None, "reason": "offline"}

    ping_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    _pending_pings[ping_id] = fut
    started = time.perf_counter()
    payload = json.dumps({"type": "ping", "ping_id": ping_id, "ts": time.time()})
    try:
        sent = False
        stale: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
                sent = True
            except Exception:
                stale.append(ws)
        for ws in stale:
            remaining = disconnect_agent(device_id, ws)
            if remaining == 0:
                await broadcast_presence(
                    device_id, online=False, last_seen=time.time()
                )
        if not sent:
            return {"connected": False, "rtt_ms": None, "reason": "offline"}
        await asyncio.wait_for(fut, timeout)
        rtt_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        await broadcast_presence(device_id, online=True, last_seen=time.time())
        return {"connected": True, "rtt_ms": rtt_ms, "reason": None}
    except asyncio.TimeoutError:
        # Socket is registered but this agent build may not speak ping/pong.
        if agent_sockets(device_id):
            await broadcast_presence(device_id, online=True, last_seen=time.time())
            return {"connected": True, "rtt_ms": None, "reason": "no_pong"}
        return {"connected": False, "rtt_ms": None, "reason": "timeout"}
    finally:
        _pending_pings.pop(ping_id, None)


async def push_command_to_agent(command: dict) -> None:
    """Push a command to every connected desktop agent of a device (if any).

    The agent executes immediately and acks; when offline it stays pending in
    Mongo and is picked up via the heartbeat poll instead.
    """
    payload = json.dumps(
        {
            "type": "command",
            "command": {
                "id": str(command.get("_id") or command.get("id") or ""),
                "device_id": command.get("device_id"),
                "type": command.get("type"),
                "status": command.get("status"),
                "created_at": command.get("created_at"),
            },
            "ts": time.time(),
        }
    )
    device_id = command.get("device_id")
    stale: list[WebSocket] = []
    for ws in list(_agent_clients.get(device_id) or []):
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        remaining = disconnect_agent(device_id, ws)
        if remaining == 0:
            await broadcast_presence(
                device_id, online=False, last_seen=time.time()
            )


def connect(ws: WebSocket) -> None:
    _clients.add(ws)


def disconnect(ws: WebSocket) -> None:
    _clients.discard(ws)


def presence_snapshot() -> list[dict]:
    """Current in-process presence for all known machines."""
    return [
        {
            "device_id": dev,
            "online": info.get("online", False),
            "last_seen": info.get("last_seen"),
            "pc_name": info.get("pc_name"),
        }
        for dev, info in _presence.items()
    ]


def update_presence(
    device_id: str,
    *,
    online: bool,
    last_seen: float,
    pc_name: str | None = None,
) -> None:
    """Update the in-process presence map and broadcast the change."""
    prev = _presence.get(device_id)
    if prev and prev.get("online") == online:
        # Already in this state; just refresh the seen time so no spam.
        prev["last_seen"] = last_seen
        if pc_name:
            prev["pc_name"] = pc_name
        return
    _presence[device_id] = {
        "online": online,
        "last_seen": last_seen,
        "pc_name": pc_name or (prev or {}).get("pc_name"),
    }


async def broadcast_presence(
    device_id: str,
    *,
    online: bool,
    last_seen: float,
    pc_name: str | None = None,
) -> None:
    """Broadcast a `presence.changed` event to every connected client."""
    update_presence(
        device_id, online=online, last_seen=last_seen, pc_name=pc_name
    )
    await _send({
        "type": "presence.changed",
        "presence": {
            "device_id": device_id,
            "online": online,
            "last_seen": last_seen,
            "pc_name": pc_name,
        },
        "ts": time.time(),
    })


async def broadcast(report: dict) -> None:
    await _send({
        "type": "report.created",
        "report": _strip_mongo_ids(report),
        "ts": time.time(),
    })


async def broadcast_print_job(job: dict) -> None:
    """Broadcast a `print.job` event so open dashboards show it live."""
    await _send({
        "type": "print.job",
        "job": _strip_mongo_ids(job),
        "ts": time.time(),
    })


def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_process_row(row: dict) -> dict:
    username = str(row.get("username") or "").strip()
    return {
        "pid": _as_int(row.get("pid")),
        "name": str(row.get("name") or "")[:80],
        "username": username[:80] if username else None,
        "cpu_percent": _as_float(row.get("cpu_percent")),
        "memory_rss": _as_int(row.get("memory_rss")),
        "memory_percent": _as_float(row.get("memory_percent")),
        "connections": _as_int(row.get("connections")),
    }


def _as_process_lists(value) -> dict:
    """Cap and sanitize live top-process lists (not stored)."""
    if not isinstance(value, dict):
        return {"cpu": [], "ram": [], "network": []}
    out: dict[str, list] = {}
    for key in ("cpu", "ram", "network"):
        rows = value.get(key) or []
        if not isinstance(rows, list):
            out[key] = []
            continue
        clean = []
        for row in rows[:10]:
            if isinstance(row, dict) and row.get("name"):
                clean.append(_as_process_row(row))
        out[key] = clean
    return out


def _as_optional_text(value, limit: int = 160) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


async def broadcast_metrics(sample: dict) -> None:
    """Broadcast a live CPU/RAM/network + top-process sample. Not persisted."""
    device_id = str(sample.get("device_id") or "").strip()
    if not device_id:
        return
    pc_name = str(sample.get("pc_name") or "").strip() or None
    metrics = {
        "device_id": device_id,
        "pc_name": pc_name,
        "cpu_percent": _as_float(sample.get("cpu_percent")),
        "ram_percent": _as_float(sample.get("ram_percent")),
        "ram_used": _as_int(sample.get("ram_used")),
        "ram_total": _as_int(sample.get("ram_total")),
        "bytes_sent": _as_int(sample.get("bytes_sent")),
        "bytes_recv": _as_int(sample.get("bytes_recv")),
        "send_rate_bps": _as_float(sample.get("send_rate_bps")),
        "recv_rate_bps": _as_float(sample.get("recv_rate_bps")),
        "processes": _as_process_lists(sample.get("processes")),
    }
    cpu_name = _as_optional_text(sample.get("cpu_name"))
    cpu_brand = _as_optional_text(sample.get("cpu_brand"), 40)
    if cpu_name:
        metrics["cpu_name"] = cpu_name
    if cpu_brand:
        metrics["cpu_brand"] = cpu_brand
    eth_name = _as_optional_text(sample.get("eth_name"), 80)
    if eth_name:
        metrics["eth_name"] = eth_name
        metrics["eth_send_rate_bps"] = _as_float(sample.get("eth_send_rate_bps"))
        metrics["eth_recv_rate_bps"] = _as_float(sample.get("eth_recv_rate_bps"))
        kind = str(sample.get("eth_kind") or "").strip().lower()
        if kind in {"ethernet", "wifi", "other"}:
            metrics["eth_kind"] = kind
        try:
            link = int(sample.get("eth_link_mbps") or 0)
        except (TypeError, ValueError):
            link = 0
        if link > 0:
            metrics["eth_link_mbps"] = link
    await _send({
        "type": "metrics.sample",
        "metrics": metrics,
        "ts": time.time(),
    })


async def _send(payload: dict) -> None:
    message = json.dumps(payload)
    stale: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _clients.discard(ws)


def _strip_mongo_ids(report: dict) -> dict:
    out = dict(report)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out