import json
import os
import platform
import socket
import subprocess
from dataclasses import dataclass

from .win_runtime import hidden_subprocess_kwargs

# Microsoft Windows application ID on SoftwareLicensingProduct.
_WINDOWS_APP_ID = "55c92734-d682-4d71-983e-d6ec3f16059f"

_LICENSE_STATUS = {
    0: ("unlicensed", "Not activated"),
    1: ("licensed", "Activated"),
    2: ("oob_grace", "Out-of-box grace"),
    3: ("oot_grace", "Out-of-tolerance grace"),
    4: ("nongenuine_grace", "Non-genuine grace"),
    5: ("notification", "Notification"),
    6: ("extended_grace", "Extended grace"),
}


@dataclass
class OSInfo:
    system: str
    release: str
    version: str
    machine: str
    processor: str
    architecture: str
    python_version: str
    hostname: str
    platform_detail: str
    windows_activation: dict | None = None

    def to_dict(self) -> dict:
        return {
            "system": self.system,
            "release": self.release,
            "version": self.version,
            "machine": self.machine,
            "processor": self.processor,
            "architecture": self.architecture,
            "python_version": self.python_version,
            "hostname": self.hostname,
            "platform_detail": self.platform_detail,
            "windows_activation": self.windows_activation,
        }


def collect_os_info() -> OSInfo:
    """Collect OS + runtime info. Uses only stdlib `platform`/`socket`, so it
    is portable between macOS and Windows (no POSIX-only APIs).

    On Windows, also queries SoftwareLicensingProduct for activation status.
    """
    return OSInfo(
        system=platform.system(),
        release=platform.release(),
        version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor() or "unknown",
        architecture=" ".join(platform.architecture()),
        python_version=platform.python_version(),
        hostname=socket.gethostname(),
        platform_detail=platform.platform(),
        windows_activation=_collect_windows_activation(),
    )


def _collect_windows_activation() -> dict | None:
    """Windows license state from WMI. `None` on macOS/Linux or on failure."""
    if os.name != "nt":
        return None
    script = (
        f"Get-CimInstance SoftwareLicensingProduct -ErrorAction SilentlyContinue "
        f"| Where-Object {{ $_.ApplicationID -eq '{_WINDOWS_APP_ID}' "
        f"-and $_.PartialProductKey }} "
        "| Select-Object Name, Description, LicenseStatus, PartialProductKey, "
        "GracePeriodRemaining, ProductKeyChannel "
        "| ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=20.0,
    )
    return parse_windows_activation(raw)


def parse_windows_activation(raw: str) -> dict | None:
    """Turn SoftwareLicensingProduct JSON into the report `windows_activation` dict."""
    text = (raw or "").strip()
    if not text or text.lower() == "null":
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
    else:
        return None
    picked = _pick_license_row(rows)
    if picked is None:
        return None
    try:
        code = int(picked.get("LicenseStatus"))
    except (TypeError, ValueError):
        code = -1
    status, label = _LICENSE_STATUS.get(code, ("unknown", "Unknown"))
    grace = _as_nonneg_int(picked.get("GracePeriodRemaining"))
    name = _clean_text(picked.get("Name") or picked.get("Description"), 160)
    channel = _clean_text(picked.get("ProductKeyChannel"), 80)
    if not channel:
        channel = _channel_from_description(picked.get("Description") or picked.get("Name"))
    partial = _clean_text(picked.get("PartialProductKey"), 16)
    return {
        "licensed": code == 1,
        "status": status,
        "label": label,
        "name": name,
        "channel": channel,
        "partial_key": partial,
        "grace_minutes": grace,
    }


def _pick_license_row(rows: list[dict]) -> dict | None:
    """Prefer the licensed Windows SKU that has a partial product key."""
    keyed = [row for row in rows if str(row.get("PartialProductKey") or "").strip()]
    pool = keyed or rows
    if not pool:
        return None

    def _status(row: dict) -> int:
        try:
            return int(row.get("LicenseStatus"))
        except (TypeError, ValueError):
            return -1

    licensed = [row for row in pool if _status(row) == 1]
    return (licensed or pool)[0]


def _channel_from_description(raw: object) -> str | None:
    text = str(raw or "")
    for token in ("VOLUME_KMSCLIENT", "VOLUME_MAK", "OEM_SLP", "OEM_COA", "Retail", "OEM"):
        if token.lower() in text.lower():
            return token
    return None


def _clean_text(value: object, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    return text[:limit]


def _as_nonneg_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _run(cmd: list[str], timeout: float = 20.0) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""
