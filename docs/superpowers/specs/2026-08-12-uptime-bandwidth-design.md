# Day-wise uptime + internet speed + bandwidth charts

Date: 2026-08-12  
Status: approved for implementation planning

## Goal

Track **per-calendar-day PC uptime** (UTC buckets, BD display), measure **approximate internet download speed**, and show **bandwidth usage charts** on Fleet and Reports (shared machine detail).

## Decisions

| Topic | Choice |
|-------|--------|
| Day boundary | UTC (`YYYY-MM-DD`) |
| Admin display timezone | Asia/Dhaka (BD) labels for the same UTC days |
| Uptime accuracy | Agent-side accumulation (not reconstructed only from sparse reports) |
| Internet speed | Short HTTPS download probe → `download_mbps` (upload optional/null) |
| NIC bandwidth | Keep existing totals + sample rates; chart history in UI |
| UI surface | Shared `MachineDetail` (Fleet + Reports) |

## Desktop app

### Uptime module

New helper (e.g. `uptime.py`) plus local state file:

- Path: `%APPDATA%/system-info/uptime.json` on Windows; `~/.config/system-info/uptime.json` (or existing config dir pattern) on macOS.
- Each run:
  1. Read `psutil.boot_time()` and current `uptime_seconds`.
  2. Load prior state (`last_boot_time`, `last_seen_at`, `by_day`).
  3. Attribute elapsed wall time since `last_seen_at` to UTC date buckets, splitting at midnight UTC; if boot time changed, only count from max(boot, last_seen) appropriately (do not credit time while powered off).
  4. Persist updated `by_day` (retain a bounded window, e.g. last 90 UTC days).

### Report payload

```json
"uptime": {
  "boot_time": 1690000000.0,
  "uptime_seconds": 86400.0,
  "by_day": { "2026-08-11": 72000, "2026-08-12": 36000 },
  "day_timezone": "UTC"
}
```

`by_day` values are seconds the machine was powered on that UTC day (best-effort from agent runs).

### Network / internet speed

Extend existing `network` object:

| Field | Meaning |
|-------|---------|
| `bytes_sent` / `bytes_recv` | Unchanged — totals since boot |
| `send_rate_bps` / `recv_rate_bps` | Unchanged — short NIC sample |
| `download_mbps` | Approx internet download from timed HTTPS GET of a small fixed URL |
| `upload_mbps` | Optional; may be `null` if download-only probe |

Probe constraints: short timeout, fail soft (`download_mbps: null` on error), do not block report forever. Prefer a stable public test object URL (documented/configurable via env later if needed).

CLI: include uptime in full report and `--sys` (or dedicated display); print day totals in human form; print download Mbps when present.

## API

- `Report.uptime: dict | None = None` (optional, same pattern as `disk` / `network`).
- No dedicated collection or migration; Mongo stores whatever the agent posts.
- Existing `GET /reports` returns the new fields as-is.

## Admin dashboard

Shared `MachineDetail` (used by Fleet and Reports):

1. **Uptime section**
   - Current session: format `uptime_seconds` as `Xd Xh Xm`.
   - Day-wise: table or bar list of recent `by_day` entries.
   - Keys stored as UTC dates; **labels shown in Asia/Dhaka** (e.g. annotate “UTC day … · BD …” or convert display of the day label clearly so BD operators understand).
2. **Network section**
   - Keep total/rate cards; add **Internet speed** card from `download_mbps`.
   - **Bandwidth usage chart** from machine report history: lines for `send_rate_bps` / `recv_rate_bps` over time (same Recharts pattern as CPU/RAM). Optional secondary series or note for cumulative sent/recv if useful without cluttering.

Sidebar / list rows: optional compact uptime or Mbps is nice-to-have; not required for v1 if detail pane covers it.

## Error handling

- Missing `uptime` / `download_mbps` on old reports: UI shows “—” / hide empty charts.
- Speed probe failure: null field, report still saves.
- Corrupt uptime state file: reset and start fresh.

## Testing

- Unit tests: UTC midnight split, reboot detection, versioned `by_day` merge.
- Network: mock HTTP for Mbps calculation; existing NIC tests unchanged.
- Dashboard types updated in `api.ts`; no new API routes required.

## Out of scope

- Configurable org timezone beyond BD display.
- Full Ookla / bidirectional speedtest CLI.
- Server-side day reconstruction as the sole source of truth.
- Separate Machines collection for uptime.

## Acceptance

- New desktop reports include `uptime.by_day` (UTC) and usually `network.download_mbps`.
- API accepts and returns them.
- Fleet and Reports machine detail show day-wise uptime (BD-aware labels) and a bandwidth usage chart.
