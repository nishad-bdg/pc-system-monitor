import re
from dataclasses import dataclass

import psutil

_BASE_DEVICE_RE = re.compile(r"/dev/(disk\d*|sd[a-z]*|nvme\d+n\d+|vd[a-z]*|mmcblk\d+|xvd[a-z]*)")


@dataclass
class DiskPartition:
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "mountpoint": self.mountpoint,
            "fstype": self.fstype,
            "total": self.total,
            "used": self.used,
            "free": self.free,
            "percent": self.percent,
        }


@dataclass
class DiskDevice:
    device: str
    total: int
    used: int
    free: int
    percent: float

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "total": self.total,
            "used": self.used,
            "free": self.free,
            "percent": self.percent,
        }


@dataclass
class DiskInfo:
    devices: list
    partitions: list

    def to_dict(self) -> dict:
        return {
            "devices": [d.to_dict() for d in self.devices],
            "partitions": [p.to_dict() for p in self.partitions],
        }


def _base_device(device: str) -> str:
    """Map a partition device to its physical device for aggregation."""
    if re.match(r"^[A-Za-z]:[\\/]", device):
        return device[:2]
    match = _BASE_DEVICE_RE.match(device)
    return match.group(0) if match else device


def _is_real_device(device: str) -> bool:
    if re.match(r"^[A-Za-z]:[\\/]", device):
        return True
    return _BASE_DEVICE_RE.match(device) is not None


def collect_disk_info() -> DiskInfo:
    """Collect partitions and aggregate totals per physical storage device.
    Skips virtual/network filesystems; portable across macOS and Windows."""
    partitions: list = []
    seen: set = set()
    for part in psutil.disk_partitions(all=True):
        if not _is_real_device(part.device):
            continue
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        partitions.append(
            DiskPartition(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            )
        )

    devices: dict = {}
    for p in partitions:
        base = _base_device(p.device)
        if base not in devices:
            devices[base] = []
        devices[base].append(p)

    result: list = []
    for base, parts in devices.items():
        totals = {p.total for p in parts}
        if len(totals) == 1:
            # Shared container (e.g. macOS APFS): all volumes report the same
            # capacity/free, so report the container as a single device.
            total = parts[0].total
            free = min(p.free for p in parts)
            used = total - free
        else:
            total = sum(p.total for p in parts)
            used = sum(p.used for p in parts)
            free = sum(p.free for p in parts)
        result.append(
            DiskDevice(
                device=base,
                total=total,
                used=used,
                free=free,
                percent=(used / total * 100) if total else 0.0,
            )
        )

    return DiskInfo(
        devices=sorted(result, key=lambda d: d.device),
        partitions=sorted(partitions, key=lambda p: p.device),
    )