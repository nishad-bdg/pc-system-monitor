"""Remote-command execution for the desktop agent.

Receives commands from the API over two channels:

1. **WebSocket (primary, immediate):** the always-on watcher keeps a `/ws/agent`
   socket open (API key as subprotocol). The API pushes `{"type":"command",
   "command": {...}}` the moment an admin requests it, so the machine acts at
   once. The agent replies `{"type":"command.ack", ...}` over the same socket.
   `collect` runs on a daemon thread and HTTP-acks when the save finishes so
   ping/command traffic is not blocked for 10–30s. `reconnect` acks without
   dropping a live socket; heartbeat fallback calls `kick()` to skip backoff.

2. **Heartbeat poll (fallback):** the heartbeat response also echoes pending
   commands, so a one-shot `--heartbeat` run or a briefly-disconnected agent
   still picks them up. The outcome is reported via HTTP `POST /commands/{id}/ack`.
   `collect` runs inline here (already on the worker thread).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading

import requests

REQUEST_TIMEOUT = 15


def _windows_shutdown_exe() -> str:
    root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    return os.path.join(root, "System32", "shutdown.exe")


def _run_windows(args: list[str]) -> bool:
    """Launch a detached Windows command with no console window.

    CREATE_NO_WINDOW is required for the frozen tray app (no inherited
    console handles); without it Popen can fail with WinError 6.
    """
    try:
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "close_fds": True,
        }
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if flags:
            kwargs["creationflags"] = flags
        subprocess.Popen(args, **kwargs)
        return True
    except OSError:
        return False


def restart_machine() -> bool:
    """Reboot the machine. Windows only (`shutdown.exe /r /t 5 /f`).

    Returns True if the restart was *initiated*. Non-Windows platforms
    return False without spawning a process.
    """
    if os.name != "nt":
        return False
    return _run_windows(
        [
            _windows_shutdown_exe(),
            "/r",
            "/t",
            "5",
            "/f",
            "/c",
            "System Info: remote restart requested",
        ]
    )


def shutdown_machine() -> bool:
    """Power off the machine. Windows only (`shutdown.exe /s /t 5 /f`)."""
    if os.name != "nt":
        return False
    return _run_windows(
        [
            _windows_shutdown_exe(),
            "/s",
            "/t",
            "5",
            "/f",
            "/c",
            "System Info: remote shutdown requested",
        ]
    )


def collect_and_save(api_url: str, api_key: str, pc_name: str = "") -> tuple[bool, str | None]:
    """Run a full collect and POST /reports. Same payload as the hourly report.

    Does not run auto-update. Builds a one-shot Namespace (all collect flags
    off, watch=False) so frozen Windows argv defaults cannot force --watch.
    """
    import argparse

    from . import cli

    args = argparse.Namespace(
        heartbeat=False,
        print_jobs=False,
        os=False,
        ip=False,
        geo=False,
        sys=False,
        disk=False,
        printers=False,
        network=False,
        security=False,
        health=False,
        emails=False,
        processes=False,
        no_save=True,
        json=False,
        watch=False,
        check_update=False,
        auto_update=False,
        version=False,
        api_url=api_url,
        api_key=api_key,
        pc_name=pc_name or "",
    )
    try:
        data = cli.collect_all(args)
        report_id = cli.save_report(data, api_url, api_key)
    except Exception:
        return False, "collect failed"
    if report_id is None:
        return False, "save failed"
    return True, None


def execute_command(
    command_type: str,
    api_url: str = "",
    api_key: str = "",
    pc_name: str = "",
) -> tuple[bool, str | None]:
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
    if command_type == "collect":
        if not api_url:
            return False, "collect requires api_url"
        return collect_and_save(api_url, api_key, pc_name)
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
    on_reconnect=None,
    pc_name: str = "",
) -> None:
    """Execute any pending remote commands and ack the outcome (HTTP fallback).

    `on_update_applied` (callable, optional) is invoked after a previously
    staged app update so a running watcher can exit and let the updater batch
    swap the exe + relaunch. `collect` runs inline (this is already the
    worker thread). `on_reconnect` (callable, optional) kicks the agent
    WebSocket so it reconnects immediately instead of waiting for backoff;
    if it returns False the reconnect command is left pending.
    """
    for cmd in commands or []:
        command_type = (cmd.get("type") or "").strip()
        command_id = str(cmd.get("id") or "").strip()
        if not command_type or not command_id:
            continue
        if command_type == "reconnect":
            if not on_reconnect:
                ack_command(
                    command_id, "failed", api_url, api_key, "watcher not running"
                )
                continue
            try:
                kicked = on_reconnect()
            except Exception:
                kicked = False
            if kicked is False:
                # Agent socket not started yet; keep pending for the next poll.
                continue
            ack_command(command_id, "done", api_url, api_key)
            continue
        ok, error = execute_command(
            command_type, api_url=api_url, api_key=api_key, pc_name=pc_name
        )
        ack_command(command_id, "done" if ok else "failed", api_url, api_key, error)
        if command_type == "update" and ok and on_update_applied:
            on_update_applied()


# ---- WebSocket agent (always-on watcher, immediate command delivery) ----

WS_RECONNECT_DELAY = 30  # seconds between reconnect attempts (capped backoff base)


class WatchCommandSocket(threading.Thread):
    """Persistent `/ws/agent` connection that executes commands instantly.

    Reconnects forever with a capped backoff; sends `hello` on connect so the
    server registers this agent socket, then waits for `command` messages,
    executes them and replies with `command.ack`. The watch loop also pushes
    live `metrics` samples on this socket. `stop()` closes the loop.
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
        self._wake = threading.Event()
        self._skip_wait = False
        self._ws = None
        self._ws_lock = threading.Lock()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def kick(self) -> bool:
        """Drop the current socket (if any) and reconnect without the backoff wait.

        Used when an admin asks an offline-looking PC to reconnect: heartbeat
        delivers `reconnect`, this skips the 30s delay so `/ws/agent` comes
        back as soon as the PC has internet.
        """
        with self._ws_lock:
            self._skip_wait = True
            ws = self._ws
            self._wake.set()
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        return True

    def _ws_url(self) -> str:
        base = self.api_url.rstrip("/")
        if base.startswith("https://"):
            return f"wss://{base[len('https://'):]}/ws/agent"
        if base.startswith("http://"):
            return f"ws://{base[len('http://'):]}/ws/agent"
        return f"ws://{base}/ws/agent"

    def run(self) -> None:
        while not self._stop.is_set():
            with self._ws_lock:
                self._skip_wait = False
            try:
                self._session()
            except Exception:
                pass
            if self._stop.is_set():
                break
            with self._ws_lock:
                skip = self._skip_wait
                if skip:
                    continue
                self._wake.clear()
            self._wake.wait(WS_RECONNECT_DELAY)

    def _session(self) -> None:
        import websocket

        ws = websocket.create_connection(
            self._ws_url(),
            subprotocols=[self.api_key],
            timeout=REQUEST_TIMEOUT,
            enable_multithread=True,
        )
        with self._ws_lock:
            self._ws = ws
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
                if (msg or {}).get("type") == "ping":
                    try:
                        ws.send(json.dumps({
                            "type": "pong",
                            "ping_id": msg.get("ping_id"),
                        }))
                    except Exception:
                        pass
                    continue
                if (msg or {}).get("type") == "command":
                    command = msg.get("command") or {}
                    command_type = str(command.get("type") or "").strip()
                    command_id = str(command.get("id") or "").strip()
                    if command_type and command_id:
                        if command_type == "reconnect":
                            # Socket is already up; ack without dropping it.
                            self._send_ack(ws, command_id, True, None)
                            continue
                        if command_type == "collect":
                            # Full collect takes 10–30s; do not block ping
                            # or other commands on this socket thread.
                            self._start_collect(command_id)
                            continue
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
            with self._ws_lock:
                if self._ws is ws:
                    self._ws = None
            try:
                ws.close()
            except Exception:
                pass

    def send_metrics(self, sample: dict) -> bool:
        """Push a live CPU/RAM/network + top-process sample over the open agent socket."""
        payload = {"type": "metrics", **sample}
        with self._ws_lock:
            ws = self._ws
            if ws is None:
                return False
            try:
                ws.send(json.dumps(payload))
                return True
            except Exception:
                return False

    def _start_collect(self, command_id: str) -> None:
        def _job() -> None:
            try:
                ok, error = execute_command(
                    "collect",
                    api_url=self.api_url,
                    api_key=self.api_key,
                    pc_name=self.pc_name or "",
                )
            except Exception:
                ok, error = False, "command execution failed"
            ack_command(
                command_id,
                "done" if ok else "failed",
                self.api_url,
                self.api_key,
                error,
            )

        threading.Thread(target=_job, daemon=True, name="collect-now").start()

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