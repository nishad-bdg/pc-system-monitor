"""Live print-job detection.

Reports newly completed print jobs to the API so the dashboard can show who
is printing what (per-hour counts in Mongo).

- Windows: `Microsoft-Windows-PrintService/Operational` Event ID 307
  ("document printed") via PowerShell, watermark = last RecordId.
- macOS: tail of `/var/log/cups/page_log` (one line per printed job),
  watermark = latest completion timestamp.

State (which jobs we already sent) is kept in `print_jobs.json` under the
user config dir so jobs fire exactly once.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import user_config_dir

_STATE_NAME = "print_jobs.json"
_STATE_PATH: Path | None = None

# Keep a bounded set of recently-sent job signatures to dedupe retries.
_MAX_SEEN = 400


@dataclass
class PrintEvent:
    printer: str
    document: str
    user: str | None = None
    pages: int | None = None
    completed_at: float | None = None
    job_id: str | None = None

    @property
    def signature(self) -> str:
        return f"{self.printer}|{self.job_id or self.document}"

    def to_dict(self) -> dict:
        return {
            "printer": self.printer,
            "document": self.document,
            "user": self.user,
            "pages": self.pages,
            "completed_at": self.completed_at,
        }


def state_path() -> Path:
    global _STATE_PATH
    if _STATE_PATH is not None:
        return _STATE_PATH
    return user_config_dir() / _STATE_NAME


def override_state_path(path: Path) -> None:
    global _STATE_PATH
    _STATE_PATH = path


def _load_state() -> dict:
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    seen = raw.get("seen") or []
    return {
        "seen": [str(s) for s in seen if isinstance(s, str)][-_MAX_SEEN:],
        "windows_record_id": raw.get("windows_record_id"),
        "macos_last_flush": raw.get("macos_last_flush"),
    }


def _save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def save_state(state: dict) -> None:
    _save_state(state)


def _is_seen(state: dict, signature: str) -> bool:
    return signature in set(state.get("seen") or [])


def _record_seen(state: dict, signature: str) -> None:
    seen = list(state.get("seen") or [])
    seen.append(signature)
    state["seen"] = seen[-_MAX_SEEN:]


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _run(cmd: list[str], timeout: float = 25.0, cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=cwd,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


# ---- Windows (PrintService event log 307) ----

_WIN_SCRIPT = r"""
Get-WinEvent -LogName 'Microsoft-Windows-PrintService/Operational' `
  -FilterXPath "*[System[(EventID=307)]]" -MaxEvents 200 -ErrorAction SilentlyContinue |
Sort-Object RecordId |
ForEach-Object {
  [pscustomobject]@{
    RecordId = $_.RecordId
    TimeCreated = ($_.TimeCreated.ToUniversalTime())
    Message = $_.Message
  }
} | ConvertTo-Json -Compress -Depth 3
"""


def collect_windows_events(last_record_id: int | None = None) -> tuple[list[PrintEvent], int]:
    """Return new print events + the last RecordId seen (Windows only)."""
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_SCRIPT])
    if not raw.strip():
        return [], last_record_id or 0
    try:
        payload = json.loads(raw)
    except ValueError:
        return [], last_record_id or 0
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return [], last_record_id or 0

    items: list[PrintEvent] = []
    newest = last_record_id or 0
    for item in payload:
        if not isinstance(item, dict):
            continue
        rid = _to_int(item.get("RecordId"))
        if rid is None:
            continue
        newest = max(newest, rid)
        if last_record_id is not None and rid <= last_record_id:
            continue
        message = str(item.get("Message") or "")
        parsed = _parse_win_307(message)
        if not parsed:
            continue
        completed = _parse_iso_ts(item.get("TimeCreated"))
        items.append(
            PrintEvent(
                printer=parsed["printer"],
                document=parsed["document"],
                user=parsed.get("user"),
                pages=parsed.get("pages"),
                completed_at=completed or time.time(),
                job_id=str(rid),
            )
        )
    return items, newest


def _parse_win_307(message: str) -> dict | None:
    """Best-effort parse of the localized 307 message.

    Typical: "Document 5, report.pdf owned by DOMAIN\\john printed on Office
    HP through port IP_192.168.1.10.  Size in bytes: 1234. Pages printed: 2."
    """
    if not message:
        return None
    document = None
    doc_match = re.search(r"\.\s*([^\n.]*?\.(?:pdf|docx?|xlsx?|pptx?|txt|jpg|png|csv|ods?|rtf|html?))", message, re.I)
    if doc_match:
        document = doc_match.group(1).strip()
    if not document:
        # Fall back to the field after "Document N," when present.
        m = re.search(r"Document\s+\d+\s*,\s*([^\s,]+)", message, re.I)
        if m:
            document = m.group(1).strip().rstrip(",")
    user = None
    um = re.search(r"owned by\s+([^.\s\\]+(?:\\[^.\s]+)?)", message, re.I)
    if um:
        user = um.group(1).strip().rstrip(",")
    printer = None
    pm = re.search(r"printed on\s+(.+?)(?:through port|\s*\.|$)", message, re.I)
    if pm:
        printer = pm.group(1).strip().rstrip(".")
    pages = None
    pg = re.search(r"Pages printed:\s*(\d+)", message, re.I)
    if pg:
        pages = _to_int(pg.group(1))
    return {"document": document, "user": user, "printer": printer, "pages": pages}


def _parse_iso_ts(value) -> float | None:
    if value is None:
        return None
    try:
        from datetime import UTC, datetime

        text = str(value).rstrip("Z")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


# ---- macOS (CUPS page_log) ----

_MACOS_PAGE_LOG = "/var/log/cups/page_log"
# printer user job-id copies pages size time1 time2 title
_MACOS_LINE_RE = re.compile(
    r"^(?P<printer>\S+)\s+(?P<user>\S+)\s+(?P<job>-?\d+)\s+(?P<copies>\d+)\s+"
    r"(?P<pages>\d+)\s+(?P<size>\d+)\s+(?P<start>\d+)\s+(?P<end>\d+)\s+(?P<title>.*)$"
)


def collect_macos_events(last_ts: float | None = None) -> tuple[list[PrintEvent], float]:
    """Return new print events from the CUPS page log + max completion seen."""
    path = Path(_MACOS_PAGE_LOG)
    if not path.is_file():
        return [], last_ts or 0.0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], last_ts or 0.0

    items: list[PrintEvent] = []
    max_ts = last_ts or 0.0
    for line in lines[-500:]:
        match = _MACOS_LINE_RE.match(line.strip())
        if not match:
            continue
        end = _to_int(match.group("end"))
        if end is None:
            continue
        ts = float(end)
        if ts > max_ts:
            max_ts = ts
        if last_ts is not None and ts <= last_ts:
            continue
        document = match.group("title").strip().strip('"')
        pages = _to_int(match.group("pages"))
        items.append(
            PrintEvent(
                printer=match.group("printer"),
                document=document or "Unknown document",
                user=match.group("user") or None,
                pages=pages,
                completed_at=ts,
                job_id=match.group("job"),
            )
        )
    # Drain the log: mark everything up to now as seen so old jobs don't re-fire.
    max_ts = max(max_ts, last_ts or 0.0)
    return items, max_ts


# ---- shared ----

def collect_new_print_events(*, now: float | None = None) -> tuple[list[PrintEvent], dict]:
    """Return events not previously reported, and the updated state dict.

    The returned state must be saved with `save_state()` even when no events
    are found (the watermark still advances).
    """
    state = _load_state()
    seen_before = set(state.get("seen") or [])
    events: list[PrintEvent] = []
    windows_new: list[PrintEvent] = []
    macos_new: list[PrintEvent] = []

    if os.name == "nt":
        items, newest = collect_windows_events(
            _to_int(state.get("windows_record_id"))
        )
        windows_new = items
        state["windows_record_id"] = newest

    if os.name != "nt":
        items, max_ts = collect_macos_events(state.get("macos_last_flush"))
        macos_new = items
        state["macos_last_flush"] = max_ts

    for evt in windows_new + macos_new:
        sig = evt.signature
        if sig in seen_before or _is_seen(state, sig):
            continue
        events.append(evt)
        _record_seen(state, sig)
    return events, state


def send_print_events(
    events: list[PrintEvent],
    api_url: str,
    api_key: str = "",
    *,
    device_id: str,
    pc_name: str,
    timeout: float = 8.0,
) -> bool:
    """POST a batch of print events to the API. Returns True on success."""
    if not events:
        return True
    if os.getenv("SYSTEM_INFO_DEBUG"):
        for evt in events:
            print(f"[print] {evt.printer}: {evt.document} ({evt.pages} pgs) {evt.user}")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "device_id": device_id,
        "pc_name": pc_name,
        "jobs": [evt.to_dict() for evt in events],
    }
    try:
        resp = subprocess_run_post(f"{api_url.rstrip('/')}/print-jobs", payload, headers, timeout)
        return resp
    except Exception as exc:  # noqa: BLE001
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print(f"[print] failed: {exc}")
        return False


def subprocess_run_post(url: str, payload: dict, headers: dict, timeout: float) -> bool:
    import requests  # deferred import keeps the module importable in tests

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return True