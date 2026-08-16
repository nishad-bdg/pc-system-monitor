import json

import pytest

from system_info import commands


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_ack_command_posts_status(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=5):
        sent["url"] = url
        sent["json"] = json
        return _FakeResponse(payload={"id": "c1"})

    monkeypatch.setattr(commands.requests, "post", fake_post)
    ok = commands.ack_command("cmd-1", "done", "http://x", "sk-key")
    assert ok is True
    assert sent["url"] == "http://x/commands/cmd-1/ack"
    assert sent["json"] == {"status": "done"}


def test_ack_command_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(commands.requests, "post", boom)
    assert commands.ack_command("cmd-1", "failed", "http://x", "sk-key") is False


def test_restart_windows(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    spawned = {}

    def fake_popen(args, **kwargs):
        spawned["args"] = args
        spawned["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(commands.subprocess, "Popen", fake_popen)
    assert commands.restart_machine() is True
    assert spawned["args"][0].lower().endswith("shutdown.exe")
    assert "/r" in spawned["args"]
    assert "/t" in spawned["args"]
    assert "/f" in spawned["args"]


def test_shutdown_windows(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    spawned = {}

    def fake_popen(args, **kwargs):
        spawned["args"] = args
        return object()

    monkeypatch.setattr(commands.subprocess, "Popen", fake_popen)
    assert commands.shutdown_machine() is True
    assert spawned["args"][0].lower().endswith("shutdown.exe")
    assert "/s" in spawned["args"]
    assert "/f" in spawned["args"]


def test_restart_non_windows_is_noop(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "posix")
    called = {"popen": 0, "run": 0}

    def fake_popen(*a, **k):
        called["popen"] += 1
        return object()

    def fake_run(*a, **k):
        called["run"] += 1
        return object()

    monkeypatch.setattr(commands.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(commands.subprocess, "run", fake_run)
    assert commands.restart_machine() is False
    assert commands.shutdown_machine() is False
    assert called == {"popen": 0, "run": 0}


def test_restart_windows_popen_failure(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "nt")

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(commands.subprocess, "Popen", boom)
    assert commands.restart_machine() is False
    assert commands.shutdown_machine() is False


def test_handle_pending_commands_acks_done(monkeypatch):
    acks = []

    def fake_ack(cid, status, url, key="", error=None):
        acks.append((cid, status))
        return True

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    monkeypatch.setattr("system_info.commands.os.name", "nt")

    spawned = {}
    monkeypatch.setattr(commands.subprocess, "Popen", lambda *a, **k: spawned.update({"args": a[0]}) or object())

    commands.handle_pending_commands(
        [{"id": "cmd-1", "type": "restart"}, {"id": "cmd-2", "type": "ignored"}],
        "http://x",
        "sk-key",
    )
    assert acks == [("cmd-1", "done"), ("cmd-2", "failed")]


def test_handle_pending_commands_acks_failed(monkeypatch):
    acks = []

    def fake_ack(cid, status, url, key="", error=None):
        acks.append((cid, status))
        return True

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    monkeypatch.setattr("system_info.commands.os.name", "posix")

    commands.handle_pending_commands(
        [{"id": "cmd-9", "type": "restart"}],
        "http://x",
        "sk-key",
    )
    assert acks == [("cmd-9", "failed")]


def test_handle_pending_commands_skips_empty(monkeypatch):
    def fake_ack(*a, **k):
        raise AssertionError("should not ack")

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    commands.handle_pending_commands([], "http://x", "sk-key")
    commands.handle_pending_commands(None, "http://x", "sk-key")


def test_execute_command_supported_types(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    spawned = {}
    monkeypatch.setattr(
        commands.subprocess, "Popen",
        lambda args, **k: spawned.update({"args": args}) or object(),
    )

    assert commands.execute_command("shutdown") == (True, None)
    assert spawned["args"][0].lower().endswith("shutdown.exe")
    assert "/s" in spawned["args"]
    assert commands.execute_command("restart") == (True, None)
    assert spawned["args"][0].lower().endswith("shutdown.exe")
    assert "/r" in spawned["args"]


def test_execute_command_restart_shutdown_rejected_off_windows(monkeypatch):
    monkeypatch.setattr("system_info.commands.os.name", "posix")
    ok, error = commands.execute_command("restart")
    assert ok is False
    assert "platform" in error
    ok, error = commands.execute_command("shutdown")
    assert ok is False
    assert "platform" in error


def test_execute_command_unsupported(monkeypatch):
    ok, error = commands.execute_command("erase-disk")
    assert ok is False
    assert "unsupported" in error


def test_collect_and_save_posts_report(monkeypatch):
    captured = {}

    def fake_collect(args):
        captured["args"] = args
        assert args.watch is False
        assert args.heartbeat is False
        return {"device_id": "d1", "pc_name": "PC1", "app_version": "0.2.21"}

    def fake_save(data, url, key=""):
        captured["data"] = data
        captured["url"] = url
        captured["key"] = key
        return "rid-1"

    monkeypatch.setattr("system_info.cli.collect_all", fake_collect)
    monkeypatch.setattr("system_info.cli.save_report", fake_save)
    ok, error = commands.collect_and_save("http://x", "sk-key", "PC1")
    assert ok is True
    assert error is None
    assert captured["url"] == "http://x"
    assert captured["key"] == "sk-key"
    assert captured["data"]["app_version"] == "0.2.21"


def test_collect_and_save_failure(monkeypatch):
    monkeypatch.setattr("system_info.cli.collect_all", lambda args: {"device_id": "d1"})
    monkeypatch.setattr("system_info.cli.save_report", lambda *a, **k: None)
    ok, error = commands.collect_and_save("http://x", "sk-key")
    assert ok is False
    assert "save" in error


def test_execute_command_collect_failure(monkeypatch):
    monkeypatch.setattr(
        commands, "collect_and_save", lambda *a, **k: (False, "save failed")
    )
    ok, error = commands.execute_command("collect", api_url="http://x", api_key="sk")
    assert ok is False
    assert "save" in error


def test_execute_command_collect_requires_api_url():
    ok, error = commands.execute_command("collect")
    assert ok is False
    assert "api_url" in error


def test_handle_pending_commands_collect(monkeypatch):
    acks = []

    def fake_ack(cid, status, url, key="", error=None):
        acks.append((cid, status))
        return True

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    monkeypatch.setattr(commands, "collect_and_save", lambda *a, **k: (True, None))
    commands.handle_pending_commands(
        [{"id": "cmd-c", "type": "collect"}],
        "http://x",
        "sk-key",
        pc_name="PC1",
    )
    assert acks == [("cmd-c", "done")]


def test_handle_pending_commands_collect_failure(monkeypatch):
    acks = []

    def fake_ack(cid, status, url, key="", error=None):
        acks.append((cid, status, error))
        return True

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    monkeypatch.setattr(
        commands, "collect_and_save", lambda *a, **k: (False, "save failed")
    )
    commands.handle_pending_commands(
        [{"id": "cmd-c", "type": "collect"}],
        "http://x",
        "sk-key",
    )
    assert acks == [("cmd-c", "failed", "save failed")]


def test_execute_command_update_stages_and_restarts(monkeypatch):
    import system_info.update as update_mod

    monkeypatch.setattr("system_info.update.is_frozen", lambda: True)
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: {"version": "9.9.9", "windows": {"url": "http://x/new.exe"}})
    monkeypatch.setattr(update_mod, "apply_update_and_restart", lambda manifest: "/tmp/apply-update-restart.cmd")

    ok, error = commands.execute_command("update")
    assert ok is True
    assert error is None


def test_execute_command_update_up_to_date(monkeypatch):
    import system_info.update as update_mod

    monkeypatch.setattr("system_info.update.is_frozen", lambda: True)
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: None)

    ok, error = commands.execute_command("update")
    assert ok is False
    assert "up to date" in error


def test_execute_command_update_non_frozen(monkeypatch):
    import system_info.update as update_mod

    monkeypatch.setattr("system_info.update.is_frozen", lambda: False)
    monkeypatch.setattr("system_info.commands.os.name", "nt")

    ok, error = commands.execute_command("update")
    assert ok is False
    assert "frozen" in error


def test_handle_pending_commands_update_triggers_restart(monkeypatch):
    import system_info.update as update_mod

    monkeypatch.setattr("system_info.update.is_frozen", lambda: True)
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: {"version": "9.9.9", "windows": {"url": "http://x/new.exe"}})
    monkeypatch.setattr(update_mod, "apply_update_and_restart", lambda manifest: "/tmp/apply-update-restart.cmd")

    acks = []

    def fake_ack(cid, status, url, key="", error=None):
        acks.append((cid, status))
        return True

    monkeypatch.setattr(commands, "ack_command", fake_ack)
    restarted = {"called": False}

    commands.handle_pending_commands(
        [{"id": "cmd-u", "type": "update"}],
        "http://x",
        "sk-key",
        on_update_applied=lambda: restarted.update(called=True),
    )
    assert acks == [("cmd-u", "done")]
    assert restarted["called"] is True


def test_ws_url_maps_scheme():
    sock = commands.WatchCommandSocket("https://api.example.com/", "sk", "d1")
    assert sock._ws_url() == "wss://api.example.com/ws/agent"
    sock2 = commands.WatchCommandSocket("http://127.0.0.1:8000", "sk", "d1")
    assert sock2._ws_url() == "ws://127.0.0.1:8000/ws/agent"


def test_ws_agent_replies_to_ping(monkeypatch):
    import json as _json

    sent = []

    class FakeWs:
        def __init__(self, inbox):
            self.inbox = list(inbox)
            self.closed = False

        def send(self, data):
            sent.append(_json.loads(data))

        def recv(self):
            if not self.inbox:
                raise OSError("closed")
            return self.inbox.pop(0)

        def close(self):
            self.closed = True

    ping_msg = _json.dumps({"type": "ping", "ping_id": "p-1", "ts": 1})
    fake_ws = FakeWs([ping_msg])

    def fake_create_connection(url, subprotocols=None, timeout=5, enable_multithread=False):
        return fake_ws

    import websocket as _ws_module

    monkeypatch.setattr(_ws_module, "create_connection", fake_create_connection)
    monkeypatch.setattr(_ws_module, "WebSocket", lambda: None)

    sock = commands.WatchCommandSocket("https://x", "sk-key", "d1")
    sock._session()

    assert sent[0]["type"] == "hello"
    pong = [m for m in sent if m.get("type") == "pong"][-1]
    assert pong["ping_id"] == "p-1"


def test_ws_agent_session_executes_and_acks(monkeypatch):
    import json as _json

    sent = []

    class FakeWs:
        def __init__(self, inbox):
            self.inbox = list(inbox)
            self.closed = False

        def send(self, data):
            sent.append(_json.loads(data))

        def recv(self):
            if not self.inbox:
                raise OSError("closed")
            return self.inbox.pop(0)

        def close(self):
            self.closed = True

    command_msg = _json.dumps(
        {"type": "command", "command": {"id": "cmd-9", "type": "shutdown"}, "ts": 1}
    )
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setattr(
        commands.subprocess, "Popen", lambda args, **k: object()
    )
    acks = []

    def fake_http_ack(*a, **k):
        acks.append(a)
        return True

    monkeypatch.setattr(commands, "ack_command", fake_http_ack)

    fake_ws = FakeWs([command_msg])

    def fake_create_connection(url, subprotocols=None, timeout=5, enable_multithread=False):
        assert url == "wss://x/ws/agent"
        assert subprotocols == ["sk-key"]
        return fake_ws

    import websocket as _ws_module

    monkeypatch.setattr(_ws_module, "create_connection", fake_create_connection)
    monkeypatch.setattr(_ws_module, "WebSocket", lambda: None)

    sock = commands.WatchCommandSocket("https://x", "sk-key", "d1")
    sock._session()  # recv raises after inbox empties -> returns

    assert sent[0]["type"] == "hello"
    assert sent[0]["device_id"] == "d1"
    ack = sent[-1]
    assert ack["type"] == "command.ack"
    assert ack["command_id"] == "cmd-9"
    assert ack["status"] == "done"
    assert fake_ws.closed is True


def test_ws_agent_update_triggers_restart_callback(monkeypatch):
    import json as _json

    import system_info.update as update_mod

    monkeypatch.setattr("system_info.update.is_frozen", lambda: True)
    monkeypatch.setattr("system_info.commands.os.name", "nt")
    monkeypatch.setattr(update_mod, "check_for_update", lambda *a, **k: {"version": "9.9.9", "windows": {"url": "http://x/new.exe"}})
    monkeypatch.setattr(update_mod, "apply_update_and_restart", lambda manifest: "/tmp/apply-update-restart.cmd")

    sent = []

    class FakeWs:
        def __init__(self, inbox):
            self.inbox = list(inbox)
            self.closed = False

        def send(self, data):
            sent.append(_json.loads(data))

        def recv(self):
            if not self.inbox:
                raise OSError("closed")
            return self.inbox.pop(0)

        def close(self):
            self.closed = True

    command_msg = _json.dumps(
        {"type": "command", "command": {"id": "cmd-u", "type": "update"}, "ts": 1}
    )
    monkeypatch.setattr(commands, "ack_command", lambda *a, **k: True)

    fake_ws = FakeWs([command_msg])

    def fake_create_connection(url, subprotocols=None, timeout=5, enable_multithread=False):
        return fake_ws

    import websocket as _ws_module

    monkeypatch.setattr(_ws_module, "create_connection", fake_create_connection)
    monkeypatch.setattr(_ws_module, "WebSocket", lambda: None)

    restarted = {"called": False}
    sock = commands.WatchCommandSocket(
        "https://x", "sk-key", "d1", on_update_applied=lambda: restarted.update(called=True)
    )
    sock._session()

    ack = [m for m in sent if m.get("type") == "command.ack"][-1]
    assert ack["status"] == "done"
    assert ack["command_id"] == "cmd-u"
    assert restarted["called"] is True


def test_ws_agent_collect_http_acks_in_background(monkeypatch):
    import json as _json
    import threading
    import time as _time

    started = threading.Event()
    proceed = threading.Event()
    http_acks = []

    def fake_collect(api_url, api_key, pc_name=""):
        started.set()
        proceed.wait(timeout=2)
        return True, None

    def fake_http_ack(cid, status, url, key="", error=None):
        http_acks.append((cid, status))
        return True

    monkeypatch.setattr(commands, "collect_and_save", fake_collect)
    monkeypatch.setattr(commands, "ack_command", fake_http_ack)

    sent = []

    class FakeWs:
        def __init__(self, inbox):
            self.inbox = list(inbox)
            self.closed = False

        def send(self, data):
            sent.append(_json.loads(data))

        def recv(self):
            if not self.inbox:
                raise OSError("closed")
            return self.inbox.pop(0)

        def close(self):
            self.closed = True

    command_msg = _json.dumps(
        {"type": "command", "command": {"id": "cmd-c", "type": "collect"}, "ts": 1}
    )
    fake_ws = FakeWs([command_msg])

    def fake_create_connection(url, subprotocols=None, timeout=5, enable_multithread=False):
        return fake_ws

    import websocket as _ws_module

    monkeypatch.setattr(_ws_module, "create_connection", fake_create_connection)
    monkeypatch.setattr(_ws_module, "WebSocket", lambda: None)

    sock = commands.WatchCommandSocket("https://x", "sk-key", "d1", pc_name="PC1")
    sock._session()

    assert started.wait(timeout=1)
    assert [m for m in sent if m.get("type") == "command.ack"] == []
    assert http_acks == []
    proceed.set()
    deadline = _time.time() + 2
    while _time.time() < deadline and not http_acks:
        _time.sleep(0.01)
    assert http_acks == [("cmd-c", "done")]