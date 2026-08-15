# Remote control — restart / shutdown

Date: 2026-08-15

## Goal

Allow an admin to **restart** or **shut down** a monitored PC from the
dashboard, delivered **in seconds** via a persistent WebSocket channel
(messenger-style), executed immediately by the always-on watcher agent, with the
acknowledged outcome visible in the dashboard.

## Non-goals

- Live `git pull` / remote command shells / arbitrary script execution.
- Making the watcher elevate itself (actions run in the watcher's — usually
  per-user — privileges; a restart needs an admin user).
- Replacing the heartbeat poll; it stays as an offline fallback.

## User flow

1. Admin opens a PC's detail (Fleet or Reports).
2. Header shows **Restart** and **Shut down** buttons (role `admin` /
   `super_admin`; `user` sees nothing). Requires a `device_id` (old reports
   without one can't be controlled).
3. Click → in-app confirm dialog → `POST /commands`.
4. API stores a `pending` command, pushes it over the agent socket immediately,
   and returns it. Button shows "sent"; inline message confirms delivery.
5. The desktop agent executes and acks; on failure an error message shows.

## Design

### Command model (Mongo `commands` collection)

```ts
{
  _id: ObjectId,
  device_id: string,
  type: "restart" | "shutdown" | "update",
  status: "pending" | "done" | "failed",
  error?: string,
  created_at: float (unix),
  acked_at?: float,
}
```

`requested_by` (username) may be added later; not stored today.

`restart`/`shutdown` reboot/power off the machine; `update` makes the desktop
app **update itself and restart** (super-admin force-update, below).

### API

- `POST /commands` — admin JWT. Body `{device_id, type}`; 422 for unknown `type`.
  Calls `realtime.push_command_to_agent(doc)` in-process; if the agent socket is
  connected the command executes immediately, else stays `pending`.
- `POST /commands/broadcast` — **super_admin** JWT only. Body `{type}`; creates a
  per-device command for every currently-connected agent socket and pushes each
  immediately (used for force-update-all). Offline agents are skipped.
- `GET /commands?device_id=&limit=` — admin JWT; newest first.
- `POST /commands/{id}/ack` — API key (same as `/reports`); body
  `{status, error?}` → sets `status` + `acked_at`; 409 if already resolved.
- `GET /heartbeat` — API key; response now includes `commands: [...]`
  (pending ones for that device — offline/HTTP fallback).
- `GET /ws/agent` — API-key WebSocket agent channel (below).

### Super-admin force-update flow

1. Dashboard Fleet → **Update all apps** (shown only to `super_admin`).
2. `POST /commands/broadcast {type:"update"}` → one `update` command per
   connected device pushed over `/ws/agent` instantly.
3. Each agent executes the `update` command (`commands.py`):
   - `force_update_and_restart()` (`update.py`) checks the manifest; if a newer
     build exists it downloads it, then `apply_update_and_restart()` writes a
     detached batch (`apply-update-restart.cmd`) that **waits for the current
     PID to exit**, swaps the exe, and relaunches `--watch` — so the *updated*
     binary comes back up.
   - The agent acks `done` over WS **and** HTTP, then `_stop_for_update()`
     stops tray + loop so the process exits and the batch can swap the file.
   - If already up to date, it acks without a restart (no `on_update_applied`).
4. Each device also ack-persisted in Mongo, so a later dashboard query of
   `/commands?device_id=` shows the per-PC outcome.

### Agent WebSocket (`/ws/agent`)

- Auth: API key via **subprotocol** (preferred, agents/browsers can't set
  arbitrary headers) or `?key=`; code 4001 on failure.
- On connect the desktop sends `{"type":"hello","device_id","pc_name"}`.
  Server registers the socket in an in-process `_agent_clients[device_id]`
  map and re-sends any `pending` commands for that device.
- Server → agent: `{"type":"command","command":{id,device_id,type,status,created_at},"ts":...}`.
- Agent → server: `{"type":"command.ack","command_id","status","error?"}` →
  server writes it to Mongo (`db.ack_command`) and the dashboard query
  invalidates.
- Push is in-process (one uvicorn worker); the offline poll + re-send-on-hello
  cover other workers/restarts.

### Desktop (`desktop-app/src/system_info/commands.py`)

- `restart_machine()` → `shutdown /r /t 5` (win) / `osascript >/dev/null
  "System Events" restart` (mac).
- `shutdown_machine()` → `shutdown /s /t 5` (win) / `osascript ... shut down`
  (mac).
- `update` command → `force_update_and_restart()` in `update.py`: manifest
  check, download, `apply_update_and_restart()` (detached batch that swaps the
  exe and relaunches `--watch` once the old PID exits). Non-frozen / non-Windows
  builds ack `failed` ("frozen Windows only").
- `execute_command(cmd) -> (ok: bool, error: str | None)` dispatches by type.
- `ack_command(...)` HTTP POSTs the ack (Mongo updated even if the socket fell).
- `handle_pending_commands(..., on_update_applied)` — heartbeat fallback; after
  a *staged* update it invokes the callback so the watcher exits and the batch
  takes over.
- `WatchCommandSocket(threading.Thread)` holds the persistent agent socket:
  - `WS_RECONNECT_DELAY = 30` (backoff resets on successful message).
  - `_ws_url()` maps `https://…` → `wss://…`, `http://…` → `ws://…`.
  - On connect sends `hello`; executes incoming `command` frames; acks over WS
    **and** HTTP. An `update` command that staged calls `on_update_applied`
    (WS path) then exits the session so the process can die.
- `watch.py::run_blocking()` starts the socket thread (with
  `on_update_applied=self._stop_for_update`) before the tray loop and
  `watch.py::stop()` stops it. `_stop_for_update()` stops the tray + loop so
  the running exe is released for the updater batch. One-shot `--heartbeat`
  handles the poll fallback without a restart (it exits on its own anyway).

### Dashboard (`dashboard/src/components/dashboard/remote-actions.tsx`)

- `RemoteActions` renders **Restart** / **Shut down** in the detail identity bar
  (`machine-detail.tsx`, `ml-auto`) for `admin`/`super_admin` only, only when
  `deviceId` is present.
- Confirm dialog (portal, same pattern as `user-nav.tsx`), `sendCommand(...)`
  helper in `lib/api.ts` → `POST /commands`. Inline "sent" confirmation / error;
  buttons stay disabled ("sent…") while a command is in flight to one PC.

## Testing

- API: `POST /commands` (403 non-admin, 422 bad type), ack (auth, update, 409 on
  resolve), agent WS auth failure (`4001`), hello-and-command flow (push →
  execute → ack persisted), pending re-send on hello.
- Desktop: ack HTTP, restart/shutdown/unsupported execution, WS URL mapping,
  socket thread executes + acks, `handle_pending_commands` with mixed results.
- Dashboard: `pnpm build`.

## Open questions

- Restart vs shutdown wording for non-admin users is moot (hidden).
- Should we add a per-PC command history UI later? (API already returns it.)