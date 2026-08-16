import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass, field

import psutil

from .win_runtime import hidden_subprocess_kwargs


@dataclass
class SystemResources:
    cpu_count: int
    cpu_count_physical: int
    cpu_percent: float
    cpu_freq_mhz: float | None
    cpu_brand: str | None
    ram_total: int
    ram_used: int
    ram_available: int
    ram_free: int
    ram_percent: float
    ram_speed_mhz: int | None
    ram_type: str | None
    swap_total: int
    swap_used: int
    swap_percent: float
    battery: dict | None
    ram_modules: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cpu_count": self.cpu_count,
            "cpu_count_physical": self.cpu_count_physical,
            "cpu_percent": self.cpu_percent,
            "cpu_freq_mhz": self.cpu_freq_mhz,
            "cpu_brand": self.cpu_brand,
            "ram_total": self.ram_total,
            "ram_used": self.ram_used,
            "ram_available": self.ram_available,
            "ram_free": self.ram_free,
            "ram_percent": self.ram_percent,
            "ram_speed_mhz": self.ram_speed_mhz,
            "ram_type": self.ram_type,
            "ram_modules": list(self.ram_modules or []),
            "swap_total": self.swap_total,
            "swap_used": self.swap_used,
            "swap_percent": self.swap_percent,
            "battery": self.battery,
        }


def _collect_battery() -> dict | None:
    """Battery info (percent, plugged, time left) — None on desktops."""
    try:
        batt = psutil.sensors_battery()
    except (NotImplementedError, OSError):
        return None
    if batt is None:
        return None
    secsleft = getattr(batt, "secsleft", -1)
    seconds_left = None
    # psutil uses -1 (unknown) and -2 (unlimited) sentinels; a sane positive
    # time-left value is real wall-clock seconds.
    if isinstance(secsleft, int) and secsleft > 0:
        seconds_left = secsleft
    plugged = bool(getattr(batt, "power_plugged", False))
    percent = float(batt.percent)
    status = "discharging"
    if plugged:
        status = "full" if percent >= 100 else "charging"
    return {
        "percent": percent,
        "power_plugged": plugged,
        "seconds_left": seconds_left,
        "status": status,
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


# Windows SMBIOSMemoryType codes -> DDR generation label
_SMBIOS_MEMORY_TYPES = {
    24: "DDR3",
    26: "DDR4",
    27: "DDR4E",
    28: "LPDDR3",
    29: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}

_BAD_IDS = frozenset({
    "",
    "unknown",
    "none",
    "n/a",
    "null",
    "0",
    "00000000",
    "to be filled by o.e.m.",
    "default string",
    "not specified",
    "empty",
})


def _clean_id(value) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in _BAD_IDS:
        return None
    return text


def _parse_size_bytes(raw) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if n > 0 else None
    text = str(raw or "").strip()
    if not text:
        return None
    match = re.search(r"([\d.]+)\s*(tib|tb|gib|gb|mib|mb|kib|kb|bytes)?", text, re.I)
    if not match:
        return None
    try:
        amount = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or "bytes").lower()
    mul = {
        "bytes": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }.get(unit, 1)
    n = int(amount * mul)
    return n if n > 0 else None


def _ram_module(
    *,
    slot: str | None = None,
    bank: str | None = None,
    manufacturer: str | None = None,
    part_number: str | None = None,
    serial: str | None = None,
    size_bytes: int | None = None,
    speed_mhz: int | None = None,
    ram_type: str | None = None,
) -> dict:
    return {
        "slot": slot,
        "bank": bank,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "serial": serial,
        "size_bytes": size_bytes,
        "speed_mhz": speed_mhz,
        "ram_type": ram_type,
    }


def _collect_macos_ram_modules() -> list[dict]:
    """Per-DIMM RAM (serial/size/type) via `system_profiler SPMemoryDataType`."""
    raw = _run(["system_profiler", "SPMemoryDataType", "-json"])
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []

    modules: list[dict] = []
    for item in payload.get("SPMemoryDataType", []):
        if not isinstance(item, dict):
            continue
        slots = item.get("SPSlotInfoList") or []
        if isinstance(slots, list) and slots:
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                status = str(slot.get("dimm_status") or "").strip().lower()
                if status in ("empty", "not populated", "no dimm"):
                    continue
                speed: int | None = None
                raw_speed = str(slot.get("dimm_speed") or slot.get("spps_memory_speed") or "").strip()
                match = re.search(r"(\d+(?:\.\d+)?)", raw_speed)
                if match:
                    speed = int(float(match.group(1)))
                size = _parse_size_bytes(
                    slot.get("dimm_size") or slot.get("spps_memory_size")
                )
                serial = _clean_id(
                    slot.get("dimm_serial_number")
                    or slot.get("dimm_serial")
                    or slot.get("spps_serial_number")
                )
                if not size and not serial and not speed:
                    continue
                modules.append(
                    _ram_module(
                        slot=_clean_id(slot.get("_name") or slot.get("dimm_type")),
                        manufacturer=_clean_id(
                            slot.get("dimm_manufacturer") or slot.get("spps_manufacturer")
                        ),
                        part_number=_clean_id(
                            slot.get("dimm_part_number") or slot.get("spps_part_number")
                        ),
                        serial=serial,
                        size_bytes=size,
                        speed_mhz=speed,
                        ram_type=_clean_id(
                            slot.get("dimm_type") or slot.get("spps_memory_type")
                        ),
                    )
                )
            continue
        # Apple Silicon / soldered: one virtual module, usually no serial.
        raw_type = _clean_id(item.get("dimm_type"))
        size = _parse_size_bytes(item.get("SPMemoryDataType_size") or item.get("dimm_size"))
        if raw_type or size:
            modules.append(_ram_module(slot="Onboard", ram_type=raw_type, size_bytes=size))
    return modules


def _collect_windows_ram_modules() -> list[dict]:
    """Per-DIMM RAM via Win32_PhysicalMemory (serial, size, type, slot)."""
    raw = _run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object BankLabel, DeviceLocator, Manufacturer, PartNumber, "
            "SerialNumber, Capacity, Speed, SMBIOSMemoryType | ConvertTo-Json",
        ]
    )
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if isinstance(payload, dict):
        payload = [payload]

    modules: list[dict] = []
    for mod in payload:
        if not isinstance(mod, dict):
            continue
        speed: int | None = None
        try:
            if mod.get("Speed"):
                speed = int(mod["Speed"])
        except (TypeError, ValueError):
            speed = None
        typ: str | None = None
        try:
            code = int(mod.get("SMBIOSMemoryType"))
        except (TypeError, ValueError):
            code = None
        if code in _SMBIOS_MEMORY_TYPES:
            typ = _SMBIOS_MEMORY_TYPES[code]
        size = _parse_size_bytes(mod.get("Capacity"))
        serial = _clean_id(mod.get("SerialNumber"))
        slot = _clean_id(mod.get("DeviceLocator"))
        bank = _clean_id(mod.get("BankLabel"))
        manufacturer = _clean_id(mod.get("Manufacturer"))
        part = _clean_id(mod.get("PartNumber"))
        if not any((size, serial, speed, slot, manufacturer)):
            continue
        modules.append(
            _ram_module(
                slot=slot,
                bank=bank,
                manufacturer=manufacturer,
                part_number=part,
                serial=serial,
                size_bytes=size,
                speed_mhz=speed,
                ram_type=typ,
            )
        )
    return modules


def _collect_ram_modules() -> list[dict]:
    if os.name == "nt":
        return _collect_windows_ram_modules()
    if platform.system() == "Darwin":
        return _collect_macos_ram_modules()
    return []


def _collect_ram_speed() -> tuple[int | None, str | None]:
    """Best-effort RAM speed (MHz) + type from the first populated module."""
    modules = _collect_ram_modules()
    speed = next((m.get("speed_mhz") for m in modules if m.get("speed_mhz")), None)
    typ = next((m.get("ram_type") for m in modules if m.get("ram_type")), None)
    return speed, typ


def _collect_cpu_brand() -> str | None:
    """Best-effort CPU vendor/brand."""
    if platform.system() == "Darwin":
        raw = _run(["system_profiler", "SPHardwareDataType", "-json"])
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        for item in payload.get("SPHardwareDataType", []):
            if not isinstance(item, dict):
                continue
            chip = str(item.get("chip_type") or "").strip()
            if chip:
                # "Apple M2" -> "Apple", "Intel Core i7-..." -> "Intel"
                return chip.split()[0] if chip.split() else chip
            proc = str(item.get("processor_name") or "").strip()
            if proc and proc.split():
                return proc.split()[0]
        return None

    if os.name == "nt":
        raw = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Processor | "
                "Select-Object Name | ConvertTo-Json",
            ]
        )
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        if isinstance(payload, dict):
            payload = [payload]
        for p in payload:
            if not isinstance(p, dict):
                continue
            name = str(p.get("Name") or "").strip()
            if not name:
                continue
            lowered = name.lower()
            if "intel" in lowered:
                return "Intel"
            if "amd" in lowered or "ryzen" in lowered or "athlon" in lowered:
                return "AMD"
            if "qualcomm" in lowered or "snapdragon" in lowered:
                return "Qualcomm"
            if name.split():
                return name.split()[0]
        return None

    return None


def collect_resources() -> SystemResources:
    """Collect CPU and memory stats via psutil (cross-platform mac/Windows)."""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    try:
        freq = psutil.cpu_freq()
        cpu_freq_mhz = freq.current if freq else None
    except (NotImplementedError, OSError):
        cpu_freq_mhz = None

    ram_modules = _collect_ram_modules()
    ram_speed_mhz = next((m.get("speed_mhz") for m in ram_modules if m.get("speed_mhz")), None)
    ram_type = next((m.get("ram_type") for m in ram_modules if m.get("ram_type")), None)
    cpu_brand = _collect_cpu_brand()

    return SystemResources(
        cpu_count=psutil.cpu_count(logical=True) or 0,
        cpu_count_physical=psutil.cpu_count(logical=False) or 0,
        cpu_percent=psutil.cpu_percent(interval=0.2),
        cpu_freq_mhz=cpu_freq_mhz,
        cpu_brand=cpu_brand,
        ram_total=vm.total,
        ram_used=vm.used,
        ram_available=vm.available,
        ram_free=vm.free,
        ram_percent=vm.percent,
        ram_speed_mhz=ram_speed_mhz,
        ram_type=ram_type,
        ram_modules=ram_modules,
        swap_total=sw.total,
        swap_used=sw.used,
        swap_percent=sw.percent,
        battery=_collect_battery(),
    )
