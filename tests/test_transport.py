import json

import pytest

from desktop_monitoring.transport import HttpPublisher, StdoutPublisher, run_once


def test_run_once_publishes_full_snapshot():
    published = []

    class CapturePublisher:
        def publish(self, snapshot: dict) -> None:
            published.append(snapshot)

    snapshot = run_once(
        publisher=CapturePublisher(),
        hostname="DESKTOP-1",
        machine_guid="GUID-1",
        adapters=[],
    )

    assert published == [snapshot]
    assert "host_id" in snapshot
    assert "network" in snapshot


def test_stdout_publisher_writes_json(capsys):
    snapshot = {"host_id": "a|b", "network": {}}

    StdoutPublisher().publish(snapshot)

    assert json.loads(capsys.readouterr().out) == snapshot


def test_http_publisher_is_an_explicit_stub():
    publisher = HttpPublisher("https://example.test/snapshots", token="secret")

    with pytest.raises(NotImplementedError):
        publisher.publish({"host_id": "a|b", "network": {}})
