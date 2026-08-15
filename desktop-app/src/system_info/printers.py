"""Collect installed printers and classify USB / network / other.

macOS uses CUPS (`lpstat`); Windows uses PowerShell `Get-Printer`.
No extra dependencies beyond the stdlib.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote


_NETWORK_HINTS = (
    "ipp://",
    "ipps://",
    "socket://",
    "http://",
    "https://",
    "smb://",
    "lpd://",
    "dnssd://",
    "wsd",
    "tcp://",
    "ip_",
    "network",
)

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IP_PREFIX_RE = re.compile(r"IP_((?:\d{1,3}\.){3}\d{1,3})", re.IGNORECASE)


@dataclass
class Printer:
    name: str
    port: str
    connection: str  # usb | network | other
    ip: str | None = None
    print_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "port": self.port,
            "ip": self.ip,
            "print_count": self.print_count,
        }


@dataclass
class PrinterInfo:
    usb: list[Printer] = field(default_factory=list)
    network: list[Printer] = field(default_factory=list)
    other: list[Printer] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.usb) + len(self.network) + len(self.other)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "usb": [p.to_dict() for p in self.usb],
            "network": [p.to_dict() for p in self.network],
            "other": [p.to_dict() for p in self.other],
        }


def classify_connection(port: str) -> str:
    """Map a device URI / Windows port name to usb | network | other."""
    value = (port or "").strip().lower()
    if not value:
        return "other"
    if "usb" in value:
        return "usb"
    if any(hint in value for hint in _NETWORK_HINTS):
        return "network"
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$", value):
        return "network"
    if re.match(r"^[a-z0-9._-]+.\w+:\d+$", value):
        return "network"
    return "other"


def extract_printer_ip(port: str, connection: str) -> str | None:
    """Pull an IPv4 address from a network printer port/URI when present."""
    if connection != "network":
        return None
    value = port or ""
    prefixed = _IP_PREFIX_RE.search(value)
    if prefixed:
        return prefixed.group(1)
    match = _IPV4_RE.search(value)
    return match.group(0) if match else None


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


def _parse_int(value: object) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _macos_print_count(name: str) -> int | None:
    """Best-effort page/impression count via IPP (ipptool), when available."""
    uri = f"ipp://localhost/printers/{quote(name)}"
    test = (
        "{\n"
        "  OPERATION Get-Printer-Attributes\n"
        "  GROUP operation-attributes-tag\n"
        "  ATTR charset attributes-charset utf-8\n"
        "  ATTR language attributes-natural-language en\n"
        f'  ATTR uri printer-uri "{uri}"\n'
        "  DISPLAY printer-impressions-completed\n"
        "  DISPLAY job-impressions-completed\n"
        "  DISPLAY printer-pages-printed\n"
        "  DISPLAY pages-completed\n"
        "}\n"
    )
    # ipptool requires a real file path (it does not accept "-" for stdin).
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ipp", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(test)
        test_path = Path(fh.name)
    try:
        result = subprocess.run(
            ["ipptool", "-t", uri, str(test_path)],
            capture_output=True,
            text=True,
            timeout=6.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            test_path.unlink()
        except OSError:
            pass
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    for attr in (
        "printer-impressions-completed",
        "job-impressions-completed",
        "printer-pages-printed",
        "pages-completed",
    ):
        # ipptool report lines look like:
        #   printer-impressions-completed (integer) = 4821
        #   printer-pages-printed (integer) = "12"
        match = re.search(
            rf"{re.escape(attr)}\s*\(?[^:=()]*\)?\s*[:=]\s*[\"']?(\d+)[\"']?",
            text,
            re.I,
        )
        if match:
            return _parse_int(match.group(1))
    return None


def _windows_print_counts() -> dict[str, int]:
    """Map printer name -> count from Get-PrinterProperty when exposed."""
    script = r"""
$out = @()
Get-Printer -ErrorAction SilentlyContinue | ForEach-Object {
  $name = $_.Name
  $count = $null
  try {
    $props = Get-PrinterProperty -PrinterName $name -ErrorAction SilentlyContinue
    foreach ($p in $props) {
      if ($p.PropertyName -match 'PageCount|PrintCount|TotalPages|Impressions|Pages Printed') {
        $n = 0
        if ([int]::TryParse([string]$p.Value, [ref]$n)) { $count = $n; break }
      }
    }
  } catch {}
  $out += [pscustomobject]@{ Name = $name; PrintCount = $count }
}
$out | ConvertTo-Json -Compress
"""
    raw = _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        timeout=20.0,
    )
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return {}
    result: dict[str, int] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        count = _parse_int(item.get("PrintCount"))
        if name and count is not None:
            result[name] = count
    return result


def _collect_macos() -> list[Printer]:
    raw = _run(["lpstat", "-v"])
    printers: list[Printer] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.lower().startswith("device for "):
            continue
        body = line[len("device for ") :]
        if ":" not in body:
            continue
        name, port = body.split(":", 1)
        name = name.strip()
        port = port.strip()
        if not name:
            continue
        connection = classify_connection(port)
        printers.append(
            Printer(
                name=name,
                port=port,
                connection=connection,
                ip=extract_printer_ip(port, connection),
                print_count=_macos_print_count(name),
            )
        )
    return printers


def _collect_windows() -> list[Printer]:
    script = (
        "Get-Printer | Select-Object Name, PortName | "
        "ConvertTo-Json -Compress"
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

    counts = _windows_print_counts()
    printers: list[Printer] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        port = str(item.get("PortName") or "").strip()
        if not name:
            continue
        connection = classify_connection(port)
        printers.append(
            Printer(
                name=name,
                port=port,
                connection=connection,
                ip=extract_printer_ip(port, connection),
                print_count=counts.get(name),
            )
        )
    return printers


def collect_printers() -> PrinterInfo:
    """List printers on this machine, grouped by connection type."""
    if os.name == "nt":
        items = _collect_windows()
    else:
        items = _collect_macos()

    info = PrinterInfo()
    for printer in sorted(items, key=lambda p: p.name.lower()):
        if printer.connection == "usb":
            info.usb.append(printer)
        elif printer.connection == "network":
            info.network.append(printer)
        else:
            info.other.append(printer)
    return info
