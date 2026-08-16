"""Collect installed printers and classify USB / network / other.

macOS uses CUPS (`lpstat`); Windows uses PowerShell `Get-Printer` plus
`Get-PrinterPort` for the real host/URL behind a port name.
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

from .win_runtime import hidden_subprocess_kwargs


# Protocol / Windows port-name hints. "network" as a bare substring is omitted
# so virtual names are not promoted. Match these against the port *and* the
# resolved Get-PrinterPort address.
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
)

# Driver/firmware lifetime counters only — not job IDs, queue length, or
# anything whose name merely contains "count".
_PAGE_COUNT_PROPERTIES = frozenset(
    {
        "pagecount",
        "printcount",
        "totalpages",
        "impressions",
        "pagesprinted",
        "config:pagecount",
    }
)

_IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
_IPV4_RE = re.compile(rf"\b(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}\b")
_IP_PREFIX_RE = re.compile(rf"IP_((?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET})", re.IGNORECASE)
_IPV4_PORT_RE = re.compile(rf"^(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}(?::\d+)?$")
_USB_PORT_RE = re.compile(r"(?:^usb\d+|usb://|\\busb\b)", re.IGNORECASE)
_UNC_RE = re.compile(r"^(?:\\\\|//)", re.IGNORECASE)
_LOCAL_PORT_RE = re.compile(
    r"^(?:lpt\d*:?|com\d*:?|file:?|nul:?|portprompt:?|xpsport:?|"
    r"shrfax:?|fax:?|dot4[\w.]*|ts\d+:?)$",
    re.IGNORECASE,
)
# FQDN (at least one dot + alphabetic label), optional :port.
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d+)?$",
    re.IGNORECASE,
)
# hostname:port without requiring a dot (not LPT1:/COM1:/FILE:).
_HOST_PORT_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9._-]{0,61}[a-z0-9])?:\d+$",
    re.IGNORECASE,
)


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
            "connection": self.connection,
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


def classify_connection(port: str, address: str = "") -> str:
    """Map a device URI / Windows port name (and optional resolved address)
    to usb | network | other.

    Windows callers should pass Get-PrinterPort's PrinterHostAddress/DeviceURL
    as ``address`` so custom-named TCP/IP ports classify as network even when
    the PortName itself has no IP hint. USB and local/virtual ports are decided
    from the port name alone so Print to PDF / FILE: / LPT1: stay ``other``.
    """
    port_value = (port or "").strip()
    addr_value = (address or "").strip()
    if _is_usb_port(port_value):
        return "usb"
    if _is_local_or_virtual_port(port_value):
        return "other"
    for value in (port_value, addr_value):
        if _is_network_endpoint(value):
            return "network"
    return "other"


def extract_printer_ip(port: str, connection: str) -> str | None:
    """Pull a valid IPv4 address from a network printer port/URI when present.

    Octets must be 0–255; values like 999.999.999.999 are rejected.
    """
    if connection != "network":
        return None
    value = port or ""
    prefixed = _IP_PREFIX_RE.search(value)
    if prefixed:
        return prefixed.group(1)
    match = _IPV4_RE.search(value)
    return match.group(0) if match else None


def _is_usb_port(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    return bool(_USB_PORT_RE.search(text.lower())) or text.lower().startswith("usb")


def _is_local_or_virtual_port(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    return bool(_LOCAL_PORT_RE.match(text))


def _is_network_endpoint(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(hint in lowered for hint in _NETWORK_HINTS):
        return True
    if _UNC_RE.match(text) or lowered.startswith("smb://"):
        return True
    if _IPV4_PORT_RE.match(text):
        return True
    if _HOSTNAME_RE.match(text):
        return True
    if _HOST_PORT_RE.match(text) and not _is_local_or_virtual_port(text.split(":")[0]):
        return True
    return False


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


def _run_powershell(script: str, timeout: float = 15.0) -> str:
    """Run a PowerShell snippet with no console window.

    Prefer Windows PowerShell (``powershell.exe``); fall back to ``pwsh`` when
    the inbox exe is missing or the PrintManagement cmdlets are unavailable.
    """
    last = ""
    for exe in ("powershell", "pwsh"):
        last = _run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=timeout,
        )
        if last.strip():
            return last
    return last


def _loads_ps_json(raw: str) -> list[dict]:
    """Normalize ConvertTo-Json output: empty / one object / array."""
    text = (raw or "").strip()
    if not text or text.lower() in {"null"}:
        return []
    try:
        payload = json.loads(text)
    except ValueError:
        return []
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


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


def _windows_printer_ports() -> dict[str, str]:
    """Map port name -> host/URL from Get-PrinterPort (Windows).

    ``PrinterHostAddress`` and ``DeviceURL`` are the authoritative location of
    a port. Custom-named Standard TCP/IP ports and WSD ports hide the IP in
    the PortName, so classification must use this map rather than the name
    alone.
    """
    script = (
        "$ports = @(Get-PrinterPort -ErrorAction SilentlyContinue | "
        "Select-Object Name, PrinterHostAddress, PortNumber, DeviceURL); "
        "if ($ports.Count -eq 0) { '[]' } else { "
        "$ports | ConvertTo-Json -Compress -Depth 4 }"
    )
    raw = _run_powershell(script, timeout=20.0)
    result: dict[str, str] = {}
    for item in _loads_ps_json(raw):
        name = str(item.get("Name") or "").strip()
        if not name:
            continue
        address = str(item.get("PrinterHostAddress") or "").strip()
        if address and address.lower() not in {"", "0", "n/a", "na"}:
            result[name] = address
            continue
        url = str(item.get("DeviceURL") or "").strip()
        if url and url.lower() not in {"", "n/a"}:
            result[name] = url
    return result


def _page_count_from_properties(props: object) -> int | None:
    """Pick a trustworthy page counter from Get-PrinterProperty rows.

    Allowlisted names only. JobCount, NumberOfJobs, JobId, and any property
    whose name merely contains "count" are ignored.
    """
    if isinstance(props, dict):
        props = [props]
    if not isinstance(props, list):
        return None
    for item in props:
        if not isinstance(item, dict):
            continue
        key = str(item.get("PropertyName") or item.get("propertyName") or "").strip().lower()
        if key not in _PAGE_COUNT_PROPERTIES:
            continue
        number = _parse_int(item.get("Value", item.get("value")))
        if number is not None:
            return number
    return None


def _windows_print_counts() -> dict[str, int]:
    """Best-effort device/driver page counter via Get-PrinterProperty.

    Windows has no standardized lifetime page count. Drivers that expose
    PageCount / PrintCount / TotalPages / Impressions / PagesPrinted /
    Config:PageCount are recorded; job IDs, queue length (JobCount), and
    any property whose name merely contains "count" are ignored.

    The number is whatever the device last reported — not "pages printed
    from this PC". Missing PrintManagement cmdlets, access errors, or
    absent properties yield no entry (callers store print_count: null).
    """
    script = r"""
$out = @()
Get-Printer -ErrorAction SilentlyContinue | ForEach-Object {
  $name = $_.Name
  $props = @()
  try {
    $props = @(Get-PrinterProperty -PrinterName $name -ErrorAction SilentlyContinue |
      Select-Object PropertyName, Value)
  } catch {}
  $out += [pscustomobject]@{ Name = $name; Properties = $props }
}
if ($out.Count -eq 0) { '[]' } else { $out | ConvertTo-Json -Compress -Depth 6 }
"""
    raw = _run_powershell(script, timeout=20.0)
    result: dict[str, int] = {}
    for item in _loads_ps_json(raw):
        name = str(item.get("Name") or "").strip()
        if not name:
            continue
        count = _page_count_from_properties(item.get("Properties"))
        if count is not None:
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
        "$p = @(Get-Printer -ErrorAction SilentlyContinue | "
        "Select-Object Name, PortName); "
        "if ($p.Count -eq 0) { '[]' } else { "
        "$p | ConvertTo-Json -Compress -Depth 4 }"
    )
    raw = _run_powershell(script, timeout=15.0)
    payload = _loads_ps_json(raw)
    if not payload:
        return []

    counts = _windows_print_counts()
    port_map = _windows_printer_ports()
    printers: list[Printer] = []
    for item in payload:
        name = str(item.get("Name") or "").strip()
        port = str(item.get("PortName") or "").strip()
        if not name:
            continue
        # Resolve Get-PrinterPort first, then classify from port name + address.
        host = port_map.get(port, "")
        connection = classify_connection(port, host)
        ip = extract_printer_ip(host, connection) or extract_printer_ip(
            port, connection
        )
        printers.append(
            Printer(
                name=name,
                port=port,
                connection=connection,
                ip=ip,
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
