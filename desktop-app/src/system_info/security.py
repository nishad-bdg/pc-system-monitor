"""Detect installed internet-security / antivirus software (macOS + Windows).

Windows: queries the Security Center (root/SecurityCenter2) via PowerShell,
which is authoritative for antivirus products. If the query returns nothing
(older Windows, missing PowerShell, restricted environments), falls back to
scanning running processes and Program Files for known vendors.

macOS: no equivalent registry exists, so we best-effort scan installed apps
(/Applications), running processes, and launch agents/daemons for known
security vendors. Built-in XProtect is reported when no third-party product
is found.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

# vendor (lowercase match token) -> display label
KNOWN_VENDORS = {
    "norton": "Norton",
    "symantec": "Symantec",
    "mcafee": "McAfee",
    "kaspersky": "Kaspersky",
    "bitdefender": "Bitdefender",
    "eset": "ESET",
    "avast": "Avast",
    "avg": "AVG",
    "sophos": "Sophos",
    "trend micro": "Trend Micro",
    "trendmicro": "Trend Micro",
    "malwarebytes": "Malwarebytes",
    "crowdstrike": "CrowdStrike",
    "sentinelone": "SentinelOne",
    "sentinel one": "SentinelOne",
    "carbon black": "Carbon Black",
    "carbonblack": "Carbon Black",
    "cylance": "Cylance",
    "webroot": "Webroot",
    "comodo": "Comodo",
    "f-secure": "F-Secure",
    "f secure": "F-Secure",
    "windows defender": "Windows Defender",
    "microsoft defender": "Microsoft Defender",
    "viper": "VIPRE",
    "intego": "Intego",
    "totalav": "TotalAV",
    "360 total security": "360 Total Security",
    "palo alto": "Palo Alto",
    "falcon": "CrowdStrike Falcon",
    "defender": "Windows Defender",
}


@dataclass
class SecurityProduct:
    name: str
    vendor: str
    active: bool | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "vendor": self.vendor, "active": self.active}


@dataclass
class SecurityInfo:
    installed: list[SecurityProduct] = field(default_factory=list)
    platform: str = ""

    @property
    def count(self) -> int:
        return len(self.installed)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "installed": [p.to_dict() for p in self.installed],
            "platform": self.platform,
        }


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _match_vendor(text: str) -> str | None:
    lowered = text.lower()
    for token, label in KNOWN_VENDORS.items():
        if token in lowered:
            return label
    return None


def _product_state_active(state: int | None) -> bool | None:
    """Windows productState: bit 16 (0x1000) set => real-time protection on."""
    if state is None:
        return None
    return bool(state & 0x1000)


def _collect_windows_security_center() -> list[SecurityProduct]:
    script = (
        "Get-CimInstance -Namespace root/SecurityCenter2 "
        "-ClassName AntiVirusProduct -ErrorAction SilentlyContinue | "
        "Select-Object displayName, productState | ConvertTo-Json -Compress"
    )
    raw = _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        timeout=15.0,
    )
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    products: list[SecurityProduct] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("displayName") or "").strip()
        if not name:
            continue
        state = item.get("productState")
        try:
            state_int = int(state) if state is not None else None
        except (TypeError, ValueError):
            state_int = None
        products.append(
            SecurityProduct(
                name=name,
                vendor=_match_vendor(name) or "Unknown",
                active=_product_state_active(state_int),
            )
        )
    return products


def _scan_processes() -> list[str]:
    names: list[str] = []
    try:
        import psutil

        for proc in psutil.process_iter(["name", "exe"]):
            info = proc.info
            name = info.get("name")
            exe = info.get("exe")
            if name:
                names.append(str(name))
            if exe:
                names.append(os.path.basename(str(exe)))
    except Exception:
        pass
    return names


def _scan_installed_paths() -> list[str]:
    """Installed-app locations for both platforms (best effort)."""
    paths: list[str] = []
    dirs = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
            value = os.getenv(env)
            if value:
                dirs.append(value)
    else:
        dirs = ["/Applications", os.path.expanduser("~/Applications")]
    for directory in dirs:
        try:
            for entry in os.listdir(directory):
                paths.append(entry)
        except OSError:
            continue
    return paths


def _scan_launch_items() -> list[str]:
    if os.name == "nt":
        return []
    dirs = [
        os.path.expanduser("~/Library/LaunchAgents"),
        "/Library/LaunchAgents",
        "/Library/LaunchDaemons",
    ]
    files: list[str] = []
    for directory in dirs:
        try:
            for entry in os.listdir(directory):
                files.append(entry)
        except OSError:
            continue
    return files


def _display_name(item: str) -> str:
    """Human-friendly name for a scanned item (strip .app, paths, process ext)."""
    base = os.path.basename(str(item))
    if base.lower().endswith(".app"):
        base = base[:-4]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base.strip()


def _scan_vendors() -> list[SecurityProduct]:
    """Best-effort vendor scan shared by macOS (and Windows fallback)."""
    found: dict[str, str] = {}  # vendor label -> display name (first match wins)
    sources = {
        "application": _scan_installed_paths(),
        "process": _scan_processes(),
        "launchd": _scan_launch_items(),
    }
    for source, items in sources.items():
        for item in items:
            vendor = _match_vendor(item)
            if vendor:
                found.setdefault(vendor, _display_name(item))

    return [
        SecurityProduct(name=display, vendor=vendor, active=None)
        for vendor, display in sorted(found.items())
    ]


def _collect_windows() -> list[SecurityProduct]:
    products = _collect_windows_security_center()
    if products:
        return products
    # Fallback when Security Center is unreachable.
    return _scan_vendors()


def _collect_macos() -> list[SecurityProduct]:
    products = _scan_vendors()
    if not products:
        products.append(
            SecurityProduct(
                name="XProtect (built-in)",
                vendor="Apple",
                active=True,
            )
        )
    return products


def collect_security_info() -> SecurityInfo:
    """Detect internet-security software on this machine."""
    if os.name == "nt":
        return SecurityInfo(installed=_collect_windows(), platform="windows")
    return SecurityInfo(installed=_collect_macos(), platform="macos")
