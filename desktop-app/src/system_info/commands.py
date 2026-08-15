"""Remote-command execution for the desktop agent (restart / shutdown).

Receives commands from the API over two channels:

1. **WebSocket (primary, immediate):** the always-on watcher keeps a `/ws/agent`
   socket open (API key as subprotocol). The API pushes `{"type":"command",
   "command": {...}}` the moment an admin requests it, so the machine acts at
   once. The agent replies `{"type":"command.ack", ...}` over the same socket.

2. **Heartbeat poll (fallback):** the heartbeat response also echoes pending
   commands, so a one-shot `--heartbeat` run or a briefly-disconnected agent
   still picks them up. The outcome is reported via HTTP `POST /commands/{id}/ack`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time

import requests

REQUEST_TIMEOUT = 15


def _run_windows(args: list[str]) -> bool:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False


def restart_machine() -> bool:
    """Reboot the machine (best-effort within the current privileges).

    Windows: `shutdown /r` (works for any interactive user).
    macOS: reboots the user session via `osascript` (System Events restart).
    Returns True if the restart was *initiated*.
    """
    try:
        if os.name == "nt":
            return _run_windows(
                ["shutdown", "/r", "/t", "5", "/c", "System Info: remote restart requested"]
            )
        script = 'tell application "System Events" to restart'
        subprocess.run(["osascript", "-e", script], timeout=15, check=True)
        return True
    except Exception:
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print("[cmd] restart failed")
        return False


def shutdown_machine() -> bool:
    """Shut the machine down (best-effort within the current privileges)."""
    try:
        if os.name == "nt":
            return _run_windows(
                ["shutdown", "/s", "/t", "5", "/c", "System Info: remote shutdown requested"]
            )
        script = 'tell application "System Events" to shut down'
        subprocess.run(["osascript", "-e", script], timeout=15, check=True)
        return True
    except Exception:
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print("[cmd] shutdown failed")
        return False


def execute_command(command_type: str) -> tuple[bool, str | None]:
    """Execute a single command type locally. Returns (ok, error)."""
    if command_type == "restart":
        ok = restart_machine()
        return ok, None if ok else "restart not possible on this platform"
    if command_type == "shutdown":
        ok = shutdown_machine()
        return ok, None if ok else "shutdown not possible on this platform"
    if command_type == "update":
        # Stage a forced app update. ok=True means a newer build was staged
        # and the app MUST restart (caller stops the watcher; the updater
        # batch swaps the exe and relaunches --watch).
        try:
            from .update import force_update_and_restart

            ok, message = force_update_and_restart(quiet=True)
        except Exception:
            return False, "update failed"
        return ok, None if ok else message
    return False, f"unsupported command: {command_type}"


def ack_command(
    command_id: str,
    status: str,
    api_url: str,
    api_key: str = "",
    error: str | None = None,
) -> bool:
    """Report command execution outcome to the API over HTTP. True on success."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {"status": status}
    if error:
        payload["error"] = error
    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/commands/{command_id}/ack",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except (requests.RequestException, ValueError, OSError) as exc:
        if os.getenv("SYSTEM_INFO_DEBUG"):
            print(f"[cmd] ack failed: {exc}")
        return False


def handle_pending_commands(
    commands: list[dict] | None,
    api_url: str,
    api_key: str = "",
    on_update_applied=None,
) -> None:
    """Execute any pending remote commands and ack the outcome (HTTP fallback).

    `on_update_applied` (callable, optional) is invoked after a previously
    staged app update so a running watcher can exit and let the updater batch
    swap the exe + relaunch.
    """
    for cmd in commands or []:
        command_type = (cmd.get("type") or "").strip()
        command_id = str(cmd.get("id") or "").strip()
        if not command_type or not command_id:
            continue
        ok, error = execute_command(command_type)
        ack_command(command_id, "done" if ok else "failed", api_url, api_key, error)
        if command_type == "update" and ok and on_update_applied:
            on_update_applied()


# ---- WebSocket agent (always-on watcher, immediate command delivery) ----

WS_RECONNECT_DELAY = 30  # seconds between reconnect attempts (capped backoff base)


class WatchCommandSocket(threading.Thread):
    """Persistent `/ws/agent` connection that executes commands instantly.

    Reconnects forever with a capped backoff; sends `hello` on connect so the
    server registers this agent socket, then waits for `command` messages,
    executes them and replies with `command.ack`. `stop()` closes the loop.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        device_id: str,
        pc_name: str | None = None,
        on_update_applied=None,
    ):
        super().__init__(name="agent-ws", daemon=True)
        self.api_url = api_url
        self.api_key = api_key
        self.device_id = device_id
        self.pc_name = pc_name
        self.on_update_applied = on_update_applied
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _ws_url(self) -> str:
        base = self.api_url.rstrip("/")
        if base.startswith("https://"):
            return f"wss://{base[len('https://'):]}/ws/agent"
        if base.startswith("http://"):
            return f"ws://{base[len('http://'):]}/ws/agent"
        return f"ws://{base}/ws/agent"

    def run(self) -> None:
        import websocket  # deferred so module stays importable without the dep

        delay = WS_RECONNECT_DELAY
        while not self._stop.is_set():
            try:
                self._session()
                delay = WS_RECONNECT_DELAY
            except Exception:
                time.sleep(min(delay, WS_RECONNECT_DELAY))
            self._stop.wait(min(delay, WS_RECONNECT_DELAY))

    def _session(self) -> None:
        import websocket

        ws = websocket.create_connection(
            self._ws_url(),
            subprotocols=[self.api_key],
            timeout=REQUEST_TIMEOUT,
            enable_multithread=True,
        )
        try:
            ws.send(json.dumps({"type": "hello", "device_id": self.device_id, "pc_name": self.pc_name}))
            while not self._stop.is_set():
                try:
                    raw = ws.recv()
                except Exception:
                    # Connection dropped: return so `run` reconnects.
                    return
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if (msg or {}).get("type") == "command":
                    command = msg.get("command") or {}
                    command_type = str(command.get("type") or "").strip()
                    command_id = str(command.get("id") or "").strip()
                    if command_type and command_id:
                        try:
                            ok, error = execute_command(command_type)
                        except Exception:
                            ok, error = False, "command execution failed"
                        self._send_ack(ws, command_id, ok, error)
                        # A staged app update needs the *running* process to
                        # exit: the updater batch waits for this PID to vanish,
                        # swaps the exe, then launches `--watch` on the new one.
                        if command_type == "update" and ok and self.on_update_applied:
                            self.on_update_applied()
                            return
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _send_ack(self, ws, command_id: str, ok: bool, error: str | None = None) -> None:
        ack = {"type": "command.ack", "command_id": command_id, "status": "done" if ok else "failed"}
        if error:
            ack["error"] = error
        try:
            ws.send(json.dumps(ack))
        except Exception:
            pass
        # Also POST the ack so the Mongo record is updated even if the WS
        # message is lost or another worker owns the DB.
        ack_command(command_id, ack["status"], self.api_url, self.api_key, error)