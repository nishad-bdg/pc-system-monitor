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
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from .win_runtime import hidden_subprocess_kwargs

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
    expiry_date: str | None = None
    expired: bool | None = None
    days_remaining: int | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vendor": self.vendor,
            "active": self.active,
            "expiry_date": self.expiry_date,
            "expired": self.expired,
            "days_remaining": self.days_remaining,
        }


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
            **hidden_subprocess_kwargs(),
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


def _parse_expiry_date(raw) -> date | None:
    """Best-effort parse of vendor licence dates (ISO, slash dates, unix, FILETIME)."""
    if raw is None or raw is False:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore").strip("\x00")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        if value > 1e16:
            try:
                unix = (value - 116444736000000000) / 10_000_000
                return datetime.fromtimestamp(unix, tz=timezone.utc).date()
            except (OSError, OverflowError, ValueError):
                return None
        if 1e12 <= value < 1e14:
            value /= 1000.0
        if 1e9 <= value < 4e9:
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc).date()
            except (OSError, OverflowError, ValueError):
                return None
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"none", "null", "n/a"}:
        return None
    iso = text[:-1] + "+00:00" if text.endswith("Z") and "T" in text else text
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        pass
    for fmt, size in (
        ("%Y-%m-%d", 10),
        ("%d/%m/%Y", 10),
        ("%d.%m.%Y", 10),
        ("%m/%d/%Y", 10),
        ("%Y%m%d", 8),
    ):
        try:
            parsed = datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
        if 1990 <= parsed.year <= 2100:
            return parsed
    return None


def _interpret_registry_expiry(name: str, value, *, today: date | None = None) -> date | None:
    """Turn a registry name/value pair into a licence end date when it looks like expiry."""
    today = today or date.today()
    key = re.sub(r"[^a-z0-9]", "", str(name).lower())
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                payload = json.loads(stripped)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                if payload.get("days_left") is not None:
                    try:
                        return today + timedelta(days=int(payload["days_left"]))
                    except (TypeError, ValueError):
                        pass
                for field_name in ("expiry_date", "expiration", "expiration_date", "expire_date"):
                    parsed = _parse_expiry_date(payload.get(field_name))
                    if parsed:
                        return parsed
    days_like = any(
        token in key
        for token in ("daysleft", "daystill", "licensedays", "daystillexpir", "licdaystill")
    )
    if days_like:
        try:
            days = int(value)
        except (TypeError, ValueError):
            days = None
        if days is not None and -365 <= days <= 4000:
            return today + timedelta(days=days)
    if any(token in key for token in ("expir", "validuntil", "subscriptionend")):
        return _parse_expiry_date(value)
    return None


def _eset_expiry_from_license(text: str) -> date | None:
    if not text:
        return None
    match = re.search(r"<ESET[\s>].*</ESET>", text, flags=re.DOTALL | re.IGNORECASE)
    xml = match.group(0) if match else text
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        found = re.search(r'EXPIRATION_DATE="([^"]+)"', text, flags=re.IGNORECASE)
        return _parse_expiry_date(found.group(1) if found else None)
    for elem in root.iter():
        raw = elem.attrib.get("EXPIRATION_DATE") or elem.attrib.get("ExpirationDate")
        local = elem.tag.rsplit("}", 1)[-1].lower()
        if not raw and local in {"expiration_date", "expirationdate"}:
            raw = (elem.text or "").strip()
        parsed = _parse_expiry_date(raw)
        if parsed:
            return parsed
    found = re.search(r'EXPIRATION_DATE="([^"]+)"', text, flags=re.IGNORECASE)
    return _parse_expiry_date(found.group(1) if found else None)


def _apply_expiry(
    product: SecurityProduct, expiry: date | None, *, today: date | None = None
) -> SecurityProduct:
    if expiry is None:
        return product
    today = today or date.today()
    days = (expiry - today).days
    product.expiry_date = expiry.isoformat()
    product.expired = days < 0
    product.days_remaining = days if days >= 0 else 0
    return product


_VENDOR_REG_FOLDERS = (
    "ESET",
    "KasperskyLab",
    "Kaspersky Lab",
    "BitDefender",
    "Bitdefender",
    "Norton",
    "Symantec",
    "McAfee",
    "AVAST Software",
    "Avast",
    "AVG",
    "Sophos",
    "Avira",
    "F-Secure",
    "Malwarebytes",
    "TrendMicro",
    "Trend Micro",
    "Webroot",
    "CrowdStrike",
    "SentinelOne",
)

_MAX_REG_DEPTH = 5


def _prefer_expiry(current: date | None, new: date | None) -> date | None:
    if new is None:
        return current
    if current is None:
        return new
    return max(current, new)


def _walk_winreg_expiry(winreg, key, vendor: str, depth: int, acc: dict[str, date]) -> None:
    index = 0
    while True:
        try:
            name, value, _typ = winreg.EnumValue(key, index)
        except OSError:
            break
        index += 1
        expiry = _interpret_registry_expiry(name, value)
        if expiry is not None:
            acc[vendor] = _prefer_expiry(acc.get(vendor), expiry)
    if depth >= _MAX_REG_DEPTH:
        return
    sub_index = 0
    while True:
        try:
            sub_name = winreg.EnumKey(key, sub_index)
        except OSError:
            break
        sub_index += 1
        try:
            with winreg.OpenKey(key, sub_name) as child:
                _walk_winreg_expiry(winreg, child, vendor, depth + 1, acc)
        except OSError:
            continue


def _eset_license_expiry(winreg) -> date | None:
    for base in (
        r"SOFTWARE\ESET\ESET Security\CurrentVersion\Info",
        r"SOFTWARE\WOW6432Node\ESET\ESET Security\CurrentVersion\Info",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as key:
                appdata, _typ = winreg.QueryValueEx(key, "AppDataDir")
        except OSError:
            continue
        path = Path(str(appdata)) / "License" / "license.lf"
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        text = ""
        for encoding in ("utf-16", "utf-8", "utf-16-le"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = data.decode("utf-8", "ignore")
        parsed = _eset_expiry_from_license(text)
        if parsed:
            return parsed
    return None


def _collect_windows_expiry_hints() -> dict[str, date]:
    """Vendor -> licence end date from registry / ESET license.lf (Windows only)."""
    hints: dict[str, date] = {}
    try:
        import winreg
    except ImportError:
        return hints

    software_bases = (r"SOFTWARE", r"SOFTWARE\WOW6432Node")
    for base in software_bases:
        for folder in _VENDOR_REG_FOLDERS:
            vendor = _match_vendor(folder) or folder
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{folder}") as key:
                    _walk_winreg_expiry(winreg, key, vendor, 0, hints)
            except OSError:
                continue
    try:
        eset = _eset_license_expiry(winreg)
    except Exception:
        eset = None
    if eset is not None:
        hints["ESET"] = _prefer_expiry(hints.get("ESET"), eset)
    return hints


def _attach_windows_expiry(
    products: list[SecurityProduct], *, today: date | None = None
) -> list[SecurityProduct]:
    if os.name != "nt":
        return products
    try:
        hints = _collect_windows_expiry_hints()
    except Exception:
        return products
    today = today or date.today()
    for product in products:
        expiry = hints.get(product.vendor)
        if expiry is None:
            haystack = f"{product.name} {product.vendor}".lower()
            for vendor, candidate in hints.items():
                if vendor.lower() in haystack:
                    expiry = candidate
                    break
        _apply_expiry(product, expiry, today=today)
    return products


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
    if not products:
        products = _scan_vendors()
    return _attach_windows_expiry(products)


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
