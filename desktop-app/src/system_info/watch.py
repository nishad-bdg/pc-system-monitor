"""Always-on daemon mode (`--watch`).

Runs continuously in the background (messenger-style): while the process is
open it keeps the PC marked online, flushes new print jobs and sends a full
report hourly — a single persistent process instead of one-shot scheduled
runs. On Windows it sits in the system tray with an Exit item so the user
can close it explicitly. Closing the app stops it; it is not a one-shot that
exits after sending data.

Timing:
  - heartbeat + print flush: every HEARTBEAT_INTERVAL (60s)
  - full hourly report: on start and then every HOUR_INTERVAL (60 min),
    aligned to the wall-clock hour so all PCs report around the same time
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time

from .device import get_or_create_device_id, resolve_pc_name
from . import version as _version
from . import cli

# Release CI used to stamp version.py with only __version__; keep a fallback
# so a frozen Windows build still starts and can show the tray.
PRODUCT_NAME = getattr(_version, "PRODUCT_NAME", None) or "System Info Reporter"

HEARTBEAT_INTERVAL = 60  # seconds — must stay well under the 300s online timeout
HOUR_INTERVAL = 3600  # seconds (60 min)


def watch_args(base: argparse.Namespace, **overrides) -> argparse.Namespace:
    """A Namespace clone with all one-shot collection flags forced off."""
    import copy

    ns = copy.copy(base)
    for name in (
        "heartbeat",
        "print_jobs",
        "os",
        "ip",
        "geo",
        "sys",
        "disk",
        "printers",
        "network",
        "security",
        "health",
        "emails",
        "no_save",
        "json",
        "watch",
    ):
        setattr(ns, name, False)
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


class WatchLoop:
    """The continuously-running background task. Exit-able from the tray."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self._stop = threading.Event()
        # Seeded at start so the immediate startup report is not duplicated;
        # the next hourly report fires ~HOUR_INTERVAL later.
        self._last_full = time.time()
        self._worker: threading.Thread | None = None

    def heartbeat(self) -> bool:
        pc_name = resolve_pc_name(self.args.pc_name)
        device_id = get_or_create_device_id(pc_name)
        response = cli.send_heartbeat(
            {"device_id": device_id, "pc_name": pc_name},
            self.args.api_url,
            self.args.api_key,
        )
        # Execute any pending remote commands (e.g. restart) reported by the API.
        if response:
            from .commands import handle_pending_commands

            try:
                handle_pending_commands(
                    response.get("commands"),
                    self.args.api_url,
                    self.args.api_key,
                    on_update_applied=self._stop_for_update,
                    pc_name=pc_name,
                )
            except Exception:
                pass
        # Flush new print jobs with the same 5-min cadence.
        try:
            cli.sync_print_jobs(self.args, device_id, pc_name, quiet=True)
        except Exception:
            pass
        return bool(response)

    def _stop_for_update(self) -> None:
        """A forced update was staged: stop this process and let it die.

        `apply_update_and_restart` already spawned a detached batch that waits
        for THIS pid to vanish, swaps the exe, and relaunches `--watch` on the
        new binary. So all that remains is to release the running exe: stop the
        tray (unblocks run_blocking) + the loop/agent, and the process exits.
        No replacement is spawned here — the updater batch does that.
        """
        icon = getattr(self, "_tray_icon", None)
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        self.stop()

    def full_report(self) -> None:
        full_args = watch_args(self.args, no_save=True)
        data = cli.collect_all(full_args)
        cli.save_report(data, self.args.api_url, self.args.api_key)
        # Quiet release check, same as one-shot hourly runs. If a newer
        # build is staged the updater batch waits for this process to exit,
        # swaps the exe, and relaunches `--watch` (tray icon).
        from .update import maybe_auto_update

        try:
            if maybe_auto_update(quiet=True):
                self._stop_for_update()
        except Exception:
            pass

    def should_full_report(self, now: float) -> bool:
        if now - self._last_full < HOUR_INTERVAL:
            return False
        self._last_full = now
        return True

    def _loop(self) -> None:
        # Heartbeat first so the PC is marked online immediately. The full
        # report can take tens of seconds (printers, battery XML, WMI) and
        # must not delay the first presence update.
        try:
            self.heartbeat()
        except Exception:
            pass
        try:
            self.full_report()
        except Exception:
            pass
        while not self._stop.is_set():
            self._stop.wait(HEARTBEAT_INTERVAL)
            if self._stop.is_set():
                break
            now = time.time()
            try:
                self.heartbeat()
            except Exception:
                pass
            if self.should_full_report(now):
                try:
                    self.full_report()
                except Exception:
                    pass

    def run_blocking(self) -> None:
        """Run the loop (optionally with a tray icon) until stopped."""
        if self._stop.is_set():
            return
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

        # Immediate command delivery: keep a /ws/agent socket open so remote
        # restart/shutdown/update commands arrive instantly instead of waiting
        # for the next heartbeat poll. A staged update exits the whole watcher
        # so the updater batch can swap the exe and relaunch --watch.
        from .commands import WatchCommandSocket

        pc_name = resolve_pc_name(self.args.pc_name)
        device_id = get_or_create_device_id(pc_name)
        agent = WatchCommandSocket(
            self.args.api_url,
            self.args.api_key,
            device_id,
            pc_name,
            on_update_applied=self._stop_for_update,
        )
        agent.start()
        self._agent_ws = agent

        _run_tray_or_wait(self, _tray_icon(self))

    def stop(self) -> None:
        self._stop.set()
        agent = getattr(self, "_agent_ws", None)
        if agent is not None:
            try:
                agent.stop()
            except Exception:
                pass

    @staticmethod
    def _current_version() -> str:
        from .version import __version__

        return __version__

    def restart_command(self) -> list[str]:
        """argv that re-launches this same watcher (used by the tray Restart).

        API URL/key/update URL are NOT re-passed on the command line: the child
        inherits the SYSTEM_INFO_* env vars already loaded from config.env, so
        nothing secret leaks into the process list. Only a CLI-given --pc-name
        is forwarded.
        """
        from .config import is_frozen

        if is_frozen():
            cmd = [os.path.abspath(sys.executable)]
        else:
            cmd = [sys.executable, "-m", "system_info"]
        cmd.append("--watch")
        if self.args.pc_name:
            cmd += ["--pc-name", str(self.args.pc_name)]
        return cmd

    def handle_restart(self) -> bool:
        """Spawn a fresh copy of this watcher, detached (tray "Restart").

        Returns True when the new process was started; the caller should then
        stop this instance so the replacement becomes the sole live watcher.
        Reuses the same detached-process flags as the Windows updater.
        """
        import subprocess

        kwargs: dict = {"close_fds": True}
        if os.name == "nt":
            flags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(self.restart_command(), **kwargs)
        except OSError:
            return False
        return True

    def handle_update_request(self) -> tuple[str, str]:
        """Run a manual update check (tray "Check for updates…").

        Returns a (message, title) pair ready to surface as a tray
        notification. A staged update sets `_exit_for_update` so the tray
        thread can stop this process; the updater batch then relaunches
        `--watch` and the new tray icon appears.
        """
        try:
            from .update import apply_update_and_restart, check_for_update

            manifest = check_for_update()
            if not manifest:
                return (
                    f"Already up to date (v{self._current_version()}).",
                    f"{PRODUCT_NAME} — no update",
                )
            new_version = str(manifest.get("version") or "unknown")
            staged = apply_update_and_restart(manifest)
            if staged:
                self._exit_for_update = True
                return (
                    f"Update v{new_version} is installing. The app will restart in the system tray.",
                    f"{PRODUCT_NAME} — update ready",
                )
            return (
                f"Update v{new_version} could not be applied on this platform. "
                "Run the setup installer to upgrade.",
                f"{PRODUCT_NAME} — update failed",
            )
        except Exception:
            return (
                "Update check failed. Verify %APPDATA%\\system-info\\config.env.",
                f"{PRODUCT_NAME} — update failed",
            )


def _run_tray_or_wait(loop: "WatchLoop", tray) -> None:
    """Block on the tray icon, or on the stop event if the tray cannot run.

    Bulletproof tray handling:
      - `icon.visible` is set ONLY from the setup callback (`_show_tray`),
        which runs after the win32 tray window + message loop exist. Setting
        it before `run()` makes `Shell_NotifyIcon(NIM_ADD)` race the window
        creation, get silently dropped, and the icon never appears while the
        heartbeat loop keeps running.
      - A watchdog re-asserts visibility in case the setup thread died
        silently (pystray's `_start_setup` thread swallows exceptions and
        `run()` keeps looping), and force-stops the tray if it stays dead so
        the retry loop below recreates the icon.
      - If the tray thread dies (Explorer crash/restart, transient shell
        issue), the icon is re-created and re-run instead of leaving the
        watcher headless or exiting.
    """
    from .win_runtime import log_watch_error

    _start_tray_watchdog(loop, tray)

    if tray is None:
        log_watch_error(
            "system tray could not be created; watcher stays running without an icon"
        )
        loop._stop.wait()
        return

    while not loop._stop.is_set():
        try:
            try:
                tray.run(setup=_show_tray)
            except TypeError:
                # Very old pystray builds lack setup=: run() then shows the
                # icon from its own setup thread, also after the loop exists.
                tray.run()
            # run() returns only after the icon has been stopped (Exit/Restart).
            break
        except Exception as exc:
            log_watch_error("system tray failed; recreating icon", exc)
        tray = _tray_icon(loop)
        if tray is None:
            loop._stop.wait()
            return
        _start_tray_watchdog(loop, tray)
        if loop._stop.wait(5):
            break
    loop._stop.set()


def _start_tray_watchdog(loop: "WatchLoop", tray) -> None:
    """Daemon thread that keeps the tray icon alive without blocking run().

    pystray's win32 backend can end up "running" with no icon if the setup
    callback thread died (exceptions there are swallowed) or if Explorer drops
    the icon. The watchdog periodically:
      1. re-asserts `visible=True` when the loop is up but the icon is not
         (safe: with a valid `_hwnd` this re-sends NIM_ADD / NIM_MODIFY);
      2. force-stops a tray whose message loop died, so `run()` returns and
         `_run_tray_or_wait` recreates the icon from scratch.
    """
    import threading as _threading

    from .win_runtime import log_watch_error

    if tray is None:
        return

    def _watch() -> None:
        silent_streak = 0
        while not loop._stop.is_set():
            try:
                running = bool(getattr(tray, "_running", False))
                visible = bool(getattr(tray, "visible", False))
                if running and not visible:
                    try:
                        tray.visible = True
                        silent_streak = 0
                    except Exception as exc:
                        silent_streak += 1
                        if silent_streak >= 3:
                            log_watch_error(
                                "tray icon not shown after 3 attempts; re-running tray",
                                exc,
                            )
                            _safe_icon_stop(tray)
                            return
                else:
                    silent_streak = 0
            except Exception as exc:
                log_watch_error("tray watchdog error", exc)
            if loop._stop.wait(10):
                return

    t = _threading.Thread(target=_watch, name="tray-watchdog", daemon=True)
    t.start()


def _safe_icon_stop(tray) -> None:
    """Stop a pystray icon without raising, e.g. from the watchdog thread."""
    try:
        if getattr(tray, "_running", False):
            tray.stop()
    except Exception:
        pass


def _show_tray(icon) -> None:
    """Make the notify icon visible and announce the product on first show."""
    icon.visible = True
    if hasattr(icon, "notify"):
        try:
            icon.notify(f"{PRODUCT_NAME} is running in the system tray.", PRODUCT_NAME)
        except Exception:
            pass


def _tray_icon(loop: "WatchLoop"):
    """Build a pystray system-tray icon with Check-update, Restart + Exit items."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception as exc:
        from .win_runtime import log_watch_error

        log_watch_error("pystray/PIL import failed; tray unavailable", exc)
        return None

    def _make_image(size: int = 64):
        # Integer coords only — some Pillow builds reject floats in ellipse().
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, size - 4, size - 4), fill=(37, 99, 235, 255))
        mid = size // 2
        d.ellipse((mid - 8, mid - 8, mid + 8, mid + 8), fill=(255, 255, 255, 255))
        return img

    def _on_exit(icon, item):
        icon.stop()
        loop.stop()

    def _notify(icon, message: str, title: str = PRODUCT_NAME):
        if icon is not None and hasattr(icon, "notify"):
            try:
                icon.notify(message, title)
            except Exception:
                pass

    def _on_check_update(icon, item):
        # Run the network + download work off the tray thread so the icon
        # stays responsive; the result is surfaced as a tray notification.
        def _work():
            outcome = loop.handle_update_request()
            message, title = outcome
            _notify(icon, message, title)
            if getattr(loop, "_exit_for_update", False):
                time.sleep(1.5)
                loop._stop_for_update()

        import threading

        threading.Thread(target=_work, daemon=True).start()

    def _on_restart(icon, item):
        if loop.handle_restart():
            # Replacement process is up; stop this instance (tray + loop + WS).
            icon.stop()
            loop.stop()
        else:
            _notify(icon, "Could not restart the app. Try Exit instead.", f"{PRODUCT_NAME} — restart failed")

    try:
        icon = pystray.Icon(
            "SystemInfoReporter",
            _make_image(),
            PRODUCT_NAME,
            menu=pystray.Menu(
                pystray.MenuItem(f"{PRODUCT_NAME} — online", lambda: None, enabled=False),
                pystray.MenuItem(
                    "Check for updates…", _on_check_update, default=True
                ),
                pystray.MenuItem("Restart", _on_restart),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", _on_exit),
            ),
        )
        # NOTE: do NOT set icon.visible=True here. On the win32 backend the
        # visible setter sends Shell_NotifyIcon(NIM_ADD) before run() creates
        # the tray window (_hwnd is still None), so the icon is silently
        # dropped and the later setup-callback set is short-circuited by the
        # `_visible == value` guard in pystray/_base.py — the app then runs
        # with no tray icon. Visibility is set only in the setup callback
        # (_show_tray), which runs after the window exists.
        # Keep a reference to the icon so the update thread can notify it.
        loop._tray_icon = icon
        return icon
    except Exception as exc:
        from .win_runtime import log_watch_error

        log_watch_error("pystray.Icon() failed; tray unavailable", exc)
        return None


def run_watch(args: argparse.Namespace) -> int:
    """Entry point for `system-info --watch`. Blocks until stopped (Exit)."""
    loop = WatchLoop(args)
    loop.run_blocking()
    return 0