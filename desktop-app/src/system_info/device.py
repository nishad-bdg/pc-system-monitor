import json
import os
import platform
import socket
import uuid
from pathlib import Path


def _config_path() -> Path:
    """Per-machine config dir, portable across macOS and Windows."""
    if os.name == "nt":
        base = os.getenv("APPDATA") or str(Path.home())
        return Path(base) / "system-info"
    base = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "system-info"


def _config_file() -> Path:
    return _config_path() / "device.json"


def get_device_name() -> str:
    return socket.gethostname() or platform.node() or "unknown-device"


def get_or_create_device_id() -> str:
    """Stable identifier for this machine, generated once and persisted.

    Using the machine's hardware address (uuid.getnode) keeps the id stable
    across reboots without extra files, falling back to a stored UUID."""
    config_file = _config_file()
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
            device_id = data.get("device_id")
            if device_id:
                return device_id
        except (OSError, ValueError):
            pass

    node = uuid.getnode()
    raw = f"{node:012x}"
    if node and node != 0xFFFFFFFFFFFF and set(raw) != {"0"}:
        # Derive a stable UUID v5 from the MAC for cross-boot stability.
        device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sysinfo-{raw}"))
    else:
        device_id = str(uuid.uuid4())

    try:
        _config_path().mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            json.dumps({"device_id": device_id, "device_name": get_device_name()})
        )
    except OSError:
        pass
    return device_id
