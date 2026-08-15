"""Collect storage (SSD/HDD) and battery health (macOS + Windows).

Windows:
  - Disks:  `Get-PhysicalDisk` (FriendlyName, MediaType, HealthStatus)
  - Battery: `powercfg /batteryreport /xml` first (broad Win8+ support;
             exposes DesignCapacity, FullChargeCapacity and CycleCount
             directly), falling back to `root/WMI` BatteryFullChargedCapacity /
             BatteryStaticData / BatteryCycleCount (+ Win32_Battery) when the
             report is unavailable.

macOS:
  - Disks:  `system_profiler SPStorageDataType` physical_drive entries
             (medium_type ssd/hdd, smart_status)
  - Battery: `system_profiler SPPowerDataType` health info
             (cycle_count, health, maximum_capacity)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .win_runtime import hidden_subprocess_kwargs


@dataclass
class DiskHealth:
    name: str
    device: str = ""
    media_type: str = "unknown"  # ssd | hdd | unknown
    brand: str | None = None  # vendor of the physical drive
    smart_status: str | None = None  # Verified | Not Supported | Failing | ...
    internal: bool | None = None
    health: str = "unknown"  # ok | warning | fail | unknown
    size_bytes: int | None = None  # total capacity of the physical disk

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "device": self.device,
            "media_type": self.media_type,
            "brand": self.brand,
            "smart_status": self.smart_status,
            "internal": self.internal,
            "health": self.health,
            "size_bytes": self.size_bytes,
        }


@dataclass
class BatteryHealth:
    cycle_count: int | None = None
    condition: str | None = None
    max_capacity_percent: int | None = None
    health_percent: int | None = None

    def to_dict(self) -> dict:
        return {
            "cycle_count": self.cycle_count,
            "condition": self.condition,
            "max_capacity_percent": self.max_capacity_percent,
            "health_percent": self.health_percent,
        }


@dataclass
class HealthInfo:
    disks: list[DiskHealth] = field(default_factory=list)
    battery: BatteryHealth | None = None

    def to_dict(self) -> dict:
        return {
            "disks": [d.to_dict() for d in self.disks],
            "battery": self.battery.to_dict() if self.battery else None,
        }


def _run(cmd: list[str], timeout: float = 15.0) -> str:
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


def _to_media_type(value: str | None) -> str:
    if not value:
        return "unknown"
    lowered = value.lower()
    if "ssd" in lowered or "solid state" in lowered or "non-rotational" in lowered:
        return "ssd"
    if "hdd" in lowered or "rotat" in lowered or "hard disk" in lowered:
        return "hdd"
    return "unknown"


def _derive_health(smart: str | None) -> str:
    if not smart:
        return "unknown"
    lowered = smart.lower()
    if "fail" in lowered:
        return "fail"
    if "verified" in lowered or "passed" in lowered or "ok" == lowered:
        return "ok"
    if "not supported" in lowered or "unsupported" in lowered:
        return "unknown"
    return "unknown"


def _extract_brand(name: str, manufacturer: str | None = None) -> str | None:
    """Best-effort vendor from a device name / manufacturer.

    Windows Get-PhysicalDisk exposes a Manufacturer (e.g. "Samsung"),
    while macOS device names embed the brand ("APPLE SSD AP0256Z" -> APPLE).
    """
    if manufacturer:
        brand = str(manufacturer).strip()
        if brand and brand.lower() not in ("unknown", "(unknown)"):
            return brand
    tokens = [t for t in name.split() if t]
    if not tokens:
        return None
    lowered = name.lower()
    # Skip words that look like the drive model, keep the leading vendor token.
    if any(kw in lowered for kw in (" ssd ", "ssd ", " hdd ", "hdd ", " solid ", " hard ")):
        vendor = tokens[0]
        return vendor if vendor else None
    # Apple drives: "APPLE SSD AP0256Z", "APPLE HDD HTS.." -> APPLE
    if lowered.startswith("apple"):
        return "Apple"
    return tokens[0]


# ---- Windows ----

_WINDOWS_EXTERNAL_BUS_TYPES = frozenset({"usb", "sd", "mmc"})
_WINDOWS_INTERNAL_BUS_TYPES = frozenset({"sata", "sas", "nvme", "raid", "scm"})


def _win_disk_internal(bus_type: object) -> bool | None:
    """Classify a Get-PhysicalDisk BusType as internal, external, or unknown."""
    bus = str(bus_type or "").strip().lower()
    if bus in _WINDOWS_EXTERNAL_BUS_TYPES:
        return False
    if bus in _WINDOWS_INTERNAL_BUS_TYPES:
        return True
    return None


def _collect_windows_disks() -> list[DiskHealth]:
    script = (
        "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, DeviceId, MediaType, HealthStatus, "
        "BusType, Manufacturer, Size | ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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

    disks: list[DiskHealth] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("FriendlyName") or "").strip()
        if not name:
            continue
        media_type = str(item.get("MediaType") or "")
        health_raw = str(item.get("HealthStatus") or "")
        health = (
            "ok"
            if health_raw.lower() in ("healthy", "ok")
            else "fail"
            if health_raw.lower() in ("unhealthy", "failed", "failing")
            else "warning"
            if health_raw.lower() in ("warning", "warning (repair)" )
            else "unknown"
        )
        try:
            size_bytes = int(item.get("Size")) if item.get("Size") is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        disks.append(
            DiskHealth(
                name=name,
                device=str(item.get("DeviceId") or ""),
                media_type=_to_media_type(media_type),
                brand=_extract_brand(name, str(item.get("Manufacturer") or "") or None),
                smart_status=None,
                internal=_win_disk_internal(item.get("BusType")),
                health=health,
                size_bytes=size_bytes,
            )
        )
    return disks


# Sentinel used by Windows when ACPI doesn't populate a capacity value.
_WINDOWS_ACPI_UNSUPPORTED = 4294967295  # (uint32)-1


def _sanitize_windows_capacity(value: object) -> int | None:
    """Return a sane positive capacity or None (0 / sentinel = unsupported)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number is None or number <= 0 or number >= _WINDOWS_ACPI_UNSUPPORTED:
        return None
    return number


def _sanitize_windows_cycle_count(value: object) -> int | None:
    """Return a non-negative cycle count, or None if missing/unsupported.

    Zero is valid for a new battery. The ACPI uint32 sentinel (4294967295)
    and negative values (e.g. powercfg -1) are treated as unknown.
    """
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number >= _WINDOWS_ACPI_UNSUPPORTED:
        return None
    return number


def _win_battery_health(full_int: int | None, designed_int: int | None) -> int | None:
    """Clamped 0..100 health % from full/design capacity, or None."""
    if full_int is None or not designed_int:
        return None
    health = int(round((full_int / designed_int) * 100))
    return max(0, min(100, health))


def _battery_condition(health_percent: int | None) -> str | None:
    if health_percent is None:
        return None
    if health_percent >= 80:
        return "Good"
    if health_percent >= 60:
        return "Warning"
    return "Poor"


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_xml_by_local_name(parent: ET.Element, name: str) -> ET.Element | None:
    for elem in parent.iter():
        if _local_xml_name(elem.tag) == name:
            return elem
    return None


def _parse_battery_xml(path: Path) -> BatteryHealth | None:
    """Parse `powercfg /batteryreport /xml` output.

    XML looks like:

        <BatteryReport>
          <Batteries>
            <Battery>
              <DesignCapacity>4800</DesignCapacity>
              <FullChargeCapacity>4400</FullChargeCapacity>
              <CycleCount>240</CycleCount>
              ...
    Battery energy values are in mWh; a desktop (no battery) omits the
    <Battery> node entirely.
    """
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError, ValueError):
        return None
    root = tree.getroot()
    battery = _find_xml_by_local_name(root, "Battery")
    if battery is None:
        return None

    def _capacity_field(tag: str) -> int | None:
        for node in battery.iter():
            if _local_xml_name(node.tag) != tag:
                continue
            value = _sanitize_windows_capacity((node.text or "").strip())
            if value is not None:
                return value
        return None

    def _cycle_field() -> int | None:
        for node in battery.iter():
            if _local_xml_name(node.tag) != "CycleCount":
                continue
            value = _sanitize_windows_cycle_count((node.text or "").strip())
            if value is not None:
                return value
        return None

    full_int = _capacity_field("FullChargeCapacity")
    designed_int = _capacity_field("DesignCapacity")
    cycle_count = _cycle_field()
    health_percent = _win_battery_health(full_int, designed_int)

    if health_percent is None and full_int is None and cycle_count is None:
        return None
    return BatteryHealth(
        cycle_count=cycle_count,
        condition=_battery_condition(health_percent),
        max_capacity_percent=health_percent,
        health_percent=health_percent,
    )


def _collect_windows_battery_powercfg() -> BatteryHealth | None:
    """Battery health via `powercfg /batteryreport /xml` (primary source)."""
    path = None
    try:
        fd, name = tempfile.mkstemp(suffix=".xml", prefix="battery-report-")
        os.close(fd)
        path = Path(name)
    except OSError:
        return None
    try:
        # powercfg writes the report to the file; stdout is empty on success.
        result = subprocess.run(
            ["powercfg", "/batteryreport", "/output", str(path), "/xml"],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        if result.returncode != 0 or not path.is_file() or path.stat().st_size == 0:
            return None
        return _parse_battery_xml(path)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _collect_windows_battery() -> BatteryHealth | None:
    """Windows battery health. powercfg battery report is authoritative; WMI
    (root/WMI MSBatteryClass + Win32_Battery) is the fallback.
    """
    from_powercfg = _collect_windows_battery_powercfg()
    if from_powercfg is not None:
        return from_powercfg

    script = (
        "$cap = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryFullChargedCapacity -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; "
        "$stat = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryStaticData -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; "
        "$cyc = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryCycleCount -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; "
        # Win32_Battery.DesignCapacity is a broadly-available fallback when the
        # root/WMI static-data class is missing or unpopulated.
        "$bios = Get-CimInstance -ClassName Win32_Battery "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "$full = $null; $design = $null; $cycle = $null; "
        "if ($null -ne $cap) { $full = [int64]$cap.FullChargedCapacity }; "
        "if ($null -ne $stat) { $design = [int64]$stat.DesignedCapacity }; "
        "if ($null -eq $design -or $design -le 0 -or $design -ge 4294967295) { "
        "if ($null -ne $bios) { $design = [int64]$bios.DesignCapacity } }; "
        "if ($null -ne $cyc) { $cycle = [int64]$cyc.CycleCount }; "
        "[pscustomobject]@{ FullChargedCapacity = $full; "
        "DesignedCapacity = $design; CycleCount = $cycle } | "
        "ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=15.0,
    )
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    full_int = _sanitize_windows_capacity(payload.get("FullChargedCapacity"))
    designed_int = _sanitize_windows_capacity(payload.get("DesignedCapacity"))
    health_percent = _win_battery_health(full_int, designed_int)
    cycle_count = _sanitize_windows_cycle_count(payload.get("CycleCount"))

    if health_percent is None and full_int is None and cycle_count is None:
        return None
    return BatteryHealth(
        cycle_count=cycle_count,
        condition=_battery_condition(health_percent),
        max_capacity_percent=health_percent,
        health_percent=health_percent,
    )


# ---- macOS ----

def _collect_macos_disks() -> list[DiskHealth]:
    raw = _run(["system_profiler", "SPStorageDataType", "-json"])
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []

    seen: dict[str, DiskHealth] = {}
    for item in payload.get("SPStorageDataType", []):
        if not isinstance(item, dict):
            continue
        physical = item.get("physical_drive") or {}
        if not isinstance(physical, dict):
            continue
        name = str(physical.get("device_name") or "").strip()
        if not name or name == "Disk Image":
            continue
        device = str(item.get("bsd_name") or "")
        # Strip partition suffix (disk3s5 or disk3s1s1 -> disk3).
        disk_base = re.sub(r"(?:s\d+)+$", "", device)
        key = f"{name}|{disk_base}"
        media_type = _to_media_type(str(physical.get("medium_type") or ""))
        smart = str(physical.get("smart_status") or "") or None
        internal_raw = str(physical.get("is_internal_disk") or "").lower()
        # The volume entry carries capacity; the same physical disk shows up
        # once per partition, so take the largest as the disk's total size.
        try:
            volume_bytes = int(item.get("size_in_bytes") or 0) or None
        except (TypeError, ValueError):
            volume_bytes = None
        current = seen.get(key)
        if current is None:
            seen[key] = DiskHealth(
                name=name,
                device=disk_base,
                media_type=media_type,
                brand=_extract_brand(name),
                smart_status=smart,
                internal=True if internal_raw in ("yes", "true") else False,
                health=_derive_health(smart),
                size_bytes=volume_bytes,
            )
        elif volume_bytes and (not current.size_bytes or volume_bytes > current.size_bytes):
            current.size_bytes = volume_bytes
    return sorted(seen.values(), key=lambda d: d.name.lower())


def _collect_macos_battery() -> BatteryHealth | None:
    raw = _run(["system_profiler", "SPPowerDataType", "-json"])
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None

    for item in payload.get("SPPowerDataType", []):
        if not isinstance(item, dict):
            continue
        if item.get("_name") != "spbattery_information":
            continue
        health = item.get("sppower_battery_health_info") or {}
        if not isinstance(health, dict):
            return None

        cycle_count = None
        try:
            cycle = health.get("sppower_battery_cycle_count")
            if cycle is not None:
                cycle_count = int(str(cycle).strip())
        except (TypeError, ValueError):
            cycle_count = None

        condition = str(health.get("sppower_battery_health") or "").strip() or None
        max_cap = None
        raw_cap = str(health.get("sppower_battery_health_maximum_capacity") or "").strip()
        if raw_cap:
            match = re.search(r"(\d+)", raw_cap)
            if match:
                max_cap = min(100, max(0, int(match.group(1))))
        if cycle_count is None and condition is None and max_cap is None:
            return None
        return BatteryHealth(
            cycle_count=cycle_count,
            condition=condition,
            max_capacity_percent=max_cap,
            health_percent=max_cap,
        )
    return None


def collect_health_info() -> HealthInfo:
    """Collect storage and battery health for this machine."""
    if os.name == "nt":
        return HealthInfo(
            disks=_collect_windows_disks(),
            battery=_collect_windows_battery(),
        )
    return HealthInfo(
        disks=_collect_macos_disks(),
        battery=_collect_macos_battery(),
    )
