import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from desktop_monitoring.network.powershell import (
    PowerShellError,
    fetch_default_route_interface_index,
    fetch_net_adapters,
    run_powershell_json,
)


def test_run_powershell_json_uses_list_args_and_timeout():
    payload = [{"Name": "Wi-Fi"}]
    completed = MagicMock(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    with patch(
        "desktop_monitoring.network.powershell._powershell_executable",
        return_value="pwsh",
    ), patch(
        "desktop_monitoring.network.powershell.subprocess.run",
        return_value=completed,
    ) as run:
        result = run_powershell_json("Write-Output '[]'", timeout_seconds=7.5)
    assert result == payload
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
    assert "-NoProfile" in cmd
    assert "-Command" in cmd
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 7.5


def test_run_powershell_json_raises_on_nonzero():
    completed = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch(
        "desktop_monitoring.network.powershell._powershell_executable",
        return_value="pwsh",
    ), patch(
        "desktop_monitoring.network.powershell.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(PowerShellError):
            run_powershell_json("throw 'x'")


def test_run_powershell_json_raises_on_invalid_json():
    completed = MagicMock(returncode=0, stdout="not-json", stderr="")
    with patch(
        "desktop_monitoring.network.powershell._powershell_executable",
        return_value="pwsh",
    ), patch(
        "desktop_monitoring.network.powershell.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(PowerShellError):
            run_powershell_json("Write-Output 'x'")


def test_run_powershell_json_raises_on_timeout():
    with patch(
        "desktop_monitoring.network.powershell._powershell_executable",
        return_value="pwsh",
    ), patch(
        "desktop_monitoring.network.powershell.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="pwsh", timeout=7.5),
    ):
        with pytest.raises(PowerShellError, match="timed out after 7.5s"):
            run_powershell_json("Start-Sleep 999", timeout_seconds=7.5)


def test_fetch_net_adapters_normalizes_single_dict():
    adapter = {"Name": "Ethernet", "ifIndex": 5}
    with patch(
        "desktop_monitoring.network.powershell.run_powershell_json",
        return_value=adapter,
    ):
        result = fetch_net_adapters()
    assert result == [adapter]


def test_fetch_default_route_interface_index_null_returns_none():
    with patch(
        "desktop_monitoring.network.powershell.run_powershell_json",
        return_value=None,
    ):
        assert fetch_default_route_interface_index() is None
