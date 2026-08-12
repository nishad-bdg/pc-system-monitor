"""Day-wise uptime tracking (UTC calendar days)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .config import user_config_dir

DAY_TIMEZONE = "UTC"
MAX_DAYS = 90
_STATE_NAME = "uptime.json"


@dataclass
class UptimeInfo:
    boot_time: float
    uptime_seconds: float
    by_day: dict[str, float]
    day_timezone: str = DAY_TIMEZONE

    def to_dict(self) -> dict:
        return {
            "boot_time": self.boot_time,
            "uptime_seconds": self.uptime_seconds,
            "by_day": dict(sorted(self.by_day.items())),
            "day_timezone": self.day_timezone,
        }


def default_state_path() -> Path:
    return user_config_dir() / _STATE_NAME


def utc_day_key(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def next_utc_midnight(ts: float) -> float:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return start.timestamp() + 86400.0


def split_seconds_by_utc_day(start: float, end: float) -> dict[str, float]:
    """Attribute seconds in [start, end) to UTC YYYY-MM-DD buckets."""
    if end <= start:
        return {}
    buckets: dict[str, float] = {}
    cursor = start
    while cursor < end:
        day = utc_day_key(cursor)
        boundary = next_utc_midnight(cursor)
        chunk_end = min(end, boundary)
        buckets[day] = buckets.get(day, 0.0) + (chunk_end - cursor)
        cursor = chunk_end
    return buckets


def merge_by_day(
    existing: dict[str, float],
    delta: dict[str, float],
    *,
    max_days: int = MAX_DAYS,
    now: float | None = None,
) -> dict[str, float]:
    merged = dict(existing)
    for day, seconds in delta.items():
        merged[day] = merged.get(day, 0.0) + float(seconds)
    if max_days <= 0:
        return merged
    ref = now if now is not None else time.time()
    cutoff_day = utc_day_key(ref - max_days * 86400.0)
    return {d: s for d, s in merged.items() if d >= cutoff_day}


def load_state(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    by_day = raw.get("by_day") or {}
    if not isinstance(by_day, dict):
        by_day = {}
    cleaned = {}
    for k, v in by_day.items():
        try:
            cleaned[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return {
        "last_boot_time": raw.get("last_boot_time"),
        "last_seen_at": raw.get("last_seen_at"),
        "by_day": cleaned,
    }


def save_state(path: Path, *, boot_time: float, seen_at: float, by_day: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_boot_time": boot_time,
        "last_seen_at": seen_at,
        "by_day": dict(sorted(by_day.items())),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def period_start(
    *,
    boot_time: float,
    now: float,
    last_boot_time: float | None,
    last_seen_at: float | None,
) -> float:
    """Start of the on-interval to credit for this run."""
    if last_boot_time is None or last_seen_at is None:
        return boot_time
    # Reboot: do not credit offline gap.
    if abs(float(boot_time) - float(last_boot_time)) > 1.0:
        return boot_time
    start = float(last_seen_at)
    if start < boot_time:
        return boot_time
    if start > now:
        return now
    return start


def collect_uptime(
    *,
    now: float | None = None,
    boot_time: float | None = None,
    state_path: Path | None = None,
) -> UptimeInfo:
    """Update local UTC day buckets and return current uptime snapshot."""
    now_ts = time.time() if now is None else float(now)
    boot = float(psutil.boot_time() if boot_time is None else boot_time)
    path = state_path if state_path is not None else default_state_path()
    state = load_state(path)

    last_boot = state.get("last_boot_time")
    last_seen = state.get("last_seen_at")
    try:
        last_boot_f = float(last_boot) if last_boot is not None else None
    except (TypeError, ValueError):
        last_boot_f = None
    try:
        last_seen_f = float(last_seen) if last_seen is not None else None
    except (TypeError, ValueError):
        last_seen_f = None

    start = period_start(
        boot_time=boot,
        now=now_ts,
        last_boot_time=last_boot_f,
        last_seen_at=last_seen_f,
    )
    delta = split_seconds_by_utc_day(start, now_ts)
    by_day = merge_by_day(state.get("by_day") or {}, delta, now=now_ts)
    save_state(path, boot_time=boot, seen_at=now_ts, by_day=by_day)

    return UptimeInfo(
        boot_time=boot,
        uptime_seconds=max(0.0, now_ts - boot),
        by_day=by_day,
        day_timezone=DAY_TIMEZONE,
    )
