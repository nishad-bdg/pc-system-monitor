# Project context — Desktop Monitoring App

Last updated: 2026-08-12

Use this file as the source of truth for current product behavior when continuing work.
Detailed design notes also live under `docs/superpowers/specs/`.

## Purpose

Collect system info from many Windows/macOS PCs via a desktop CLI, store reports in MongoDB through a FastAPI backend, and manage/view them in a Next.js admin dashboard.

## Layout

```
desktop-app/   Python CLI (`system-info`) — collect + POST reports
api/           FastAPI + MongoDB — auth, API keys, reports
dashboard/     Next.js admin UI — Fleet + Reports
docs/          Specs/plans (superpowers)
```

## Stack

| Area | Tech |
|------|------|
| Desktop | Python 3.14, `psutil`, `requests`, `uv` |
| API | FastAPI, MongoDB, JWT + API keys, `uv` |
| Dashboard | Next.js 16, NextAuth v5, TanStack Query, Recharts, Tailwind, pnpm |

## Auth

- **Desktop → API:** `Authorization: Bearer sk-...` (API key). Create via `POST /api-keys` (admin JWT). Full secret shown only once at create time. **Admin UI for keys is not built yet** (API-only).
- **Dashboard → API:** NextAuth Credentials → `POST /auth/token` → JWT stored on session as `apiToken`.

## Data flow

```
Desktop CLI (full collect)
  → POST /reports (API key)
  → MongoDB reports collection

Admin dashboard
  → GET /reports?... (JWT)
  → groupMachines() for fleet / reports table
```

Restart the API after model/query changes; old processes strip unknown fields (e.g. `printers`, `pc_name`, `network`).

---

## Desktop app (`desktop-app/`)

### Commands

```bash
uv run system-info --api-key sk-...          # full collect + save
uv run system-info --no-save                 # print only
uv run system-info --pc-name Office-PC-3     # Windows custom name
uv run system-info --printers | --disk | --network | --sys | ...
```

Env: `SYSTEM_INFO_API_URL`, `SYSTEM_INFO_API_KEY`, `SYSTEM_INFO_PC_NAME`.

### Identity

- **`device_id`:** stable UUID from `device.py` (`get_or_create_device_id`), persisted in OS config dir (`~/.config/system-info/device.json` or `%APPDATA%/system-info`).
- **`pc_name`:**
  - **macOS:** always OS hostname (custom `--pc-name` ignored).
  - **Windows:** `--pc-name` / `SYSTEM_INFO_PC_NAME`, else hostname.

### Collected payload (full run)

| Field | Source | Notes |
|-------|--------|--------|
| `pc_name`, `device_id` | `device.py` | Always on save |
| `os` | `os_info.py` | Includes hostname |
| `private_ip`, `public_ip`, `mac_address`, `mac_addresses` | `ip.py` | |
| `location` | `geo.py` | ip-api.com |
| `resources` | `resources.py` | CPU/RAM/swap |
| `uptime` | `uptime.py` | Session + UTC day-wise on-seconds (`by_day`) |
| `network` | `network.py` | NIC totals/rates + approx `download_mbps` |

| `disk` | `disk.py` | Physical devices + partitions (mac + Win) |
| `printers` | `printers.py` | See below |
| `network` | `network.py` | Bandwidth totals + rates |

### Printers

Grouped as **usb / network / other**.

Each printer: `{ name, port, ip, print_count }`.

- **ip:** extracted from network port/URI when IPv4 present; else `null`.
- **print_count:** best-effort (macOS IPP/`ipptool`; Windows `Get-PrinterProperty`); else `null`.
- macOS: CUPS `lpstat -v`; Windows: PowerShell `Get-Printer`.

### Network bandwidth

`network: { bytes_sent, bytes_recv, send_rate_bps, recv_rate_bps, download_mbps?, upload_mbps? }` —
totals since boot + ~0.5s NIC sample rates (`psutil`). Internet Mbps is **not** probed on each report; use the admin **Live speed test** button.

### Uptime (day-wise)

`uptime: { boot_time, uptime_seconds, by_day: { "YYYY-MM-DD": seconds }, day_timezone: "UTC" }` —
agent accumulates on-seconds per UTC day in `uptime.json`; admin labels days in Asia/Dhaka (BD).

---

## API (`api/`)

### Report model extras

Optional on `Report`: `pc_name`, `device_id`, `disk`, `printers`, `network`, `uptime` (plus original OS/IP/geo/resources).

### `GET /reports` query params

| Param | Behavior |
|-------|----------|
| `limit` | 1–500 |
| `device_id` | Exact match |
| `pc_name` | Case-insensitive contains on `pc_name` **or** `os.hostname` |
| `from_ts`, `to_ts` | Unix seconds on `created_at` |
| `country` | Regex on `location.country` or `location.country_code` |
| `os` | Regex on `os.system` |

Sorted by `created_at` **descending** (newest first). Auth: admin JWT.

### Other routes

- `POST /reports` — API key; stores `source_key` prefix.
- `GET /reports/{id}` — JWT.
- Auth, users, API keys, health — unchanged pattern.

---

## Dashboard (`dashboard/`)

### Visual direction

Slate + blue: dark fleet sidebar, light detail panes. Avoid purple/glow themes.

### Routes

| Path | Purpose |
|------|---------|
| `/login` | Admin sign-in |
| `/dashboard` | **Fleet** — sidebar PC list + live detail for selected machine |
| `/reports` | **Reports browser** — filters + one row per PC |
| `/reports/[key]` | PC detail from reports (encoded machine key) |

### Fleet (`/dashboard`)

- Sidebar: filter by name, select PC, Refresh, link to Reports.
- Detail: CPU/RAM/swap tiles, **Uptime** (session + UTC day bars with BD labels), location/machine, **Storage** (device count + partition bars: blue &lt;50%, amber 50–80%, red &gt;80%), **Network bandwidth** (incl. internet Mbps + usage chart), **Printers** (USB/Network/Other with IP + print count), charts, report history.
- Shared detail UI: `src/components/dashboard/machine-detail.tsx`.

### Reports (`/reports`)

- Same slate+blue **sidebar + detail** layout as Fleet.
- Sidebar filters: date from/to, PC name, country, OS.
- **Usage sort** (highest first): Most CPU, Most RAM, Most disk space used, Most network usage (bytes sent+recv), or Last seen.
- **Min thresholds**: Min CPU %, Min RAM %, Min disk % (filters out PCs below threshold).
- Sidebar lists matching PCs with CPU/RAM/Disk/Net; main pane shows `MachineDetail`.
- Permalink: `/reports/[key]`.

### Machine grouping (`groupMachines` in `src/lib/api.ts`)

Prevents duplicate fleet rows when old reports lack `device_id`:

1. Prefer **`device_id`**
2. Else **MAC** (primary + interfaces)
3. Else **pc_name / hostname**
4. **Merge** groups that share a MAC or the same name into the strongest identity

Keys look like `id:…`, `mac:…`, `name:…` (URL-encoded for `/reports/[key]`).

### Important ops note

Dashboard **Refresh** only reloads API data. It does **not** push collect commands to desktops (agent/poll design discussed, not implemented). Re-run `system-info` on each PC for new snapshots.

---

## Windows packaging (release updates)

See `desktop-app/packaging/windows/README.md`.

- **Installer (Inno Setup):** installs exe under `%LOCALAPPDATA%\SystemInfo`, writes
  `%APPDATA%\system-info\config.env` (API URL/key/PC name/update URL), creates
  Task Scheduler job **SystemInfoReport** every 30 minutes.
- **Updates:** host a JSON release manifest (`SYSTEM_INFO_UPDATE_URL`); app checks
  on each run and stages a new exe (not live `git pull`).

---

## Tests / verify

```bash
cd desktop-app && uv run pytest
cd api && uv run pytest
cd dashboard && pnpm build
```

After pulling API changes: restart `uv run sysinfo-api`, then run desktop with a valid API key and refresh the dashboard.

---

## Specs written this cycle

- `docs/superpowers/specs/2026-08-12-multi-pc-monitoring-design.md`
- `docs/superpowers/specs/2026-08-12-printers-design.md`
- `docs/superpowers/specs/2026-08-12-network-printers-metrics-design.md`
- `docs/superpowers/specs/2026-08-12-uptime-bandwidth-design.md`
- `docs/superpowers/plans/2026-08-12-multi-pc-monitoring.md`
- `docs/superpowers/plans/2026-08-12-uptime-bandwidth.md`
