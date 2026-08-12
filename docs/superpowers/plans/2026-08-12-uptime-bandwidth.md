# Uptime + Bandwidth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship UTC day-wise uptime, approximate download Mbps, and bandwidth charts on Fleet + Reports.

**Architecture:** Desktop accumulates on-seconds per UTC day in `uptime.json`, posts `uptime` + extended `network`; API stores optional dicts; shared `MachineDetail` shows BD-labeled day bars and rate history charts.

**Tech Stack:** Python/`psutil`/`requests`, FastAPI + MongoDB, Next.js + Recharts.

## Global Constraints

- Day buckets: UTC `YYYY-MM-DD`.
- Admin labels: Asia/Dhaka (BD) for the same UTC days.
- Speed probe: short HTTPS download only; fail soft to `null`.
- UI via shared `MachineDetail` (Fleet + Reports).
- Do not commit unless the user asks.

---

### Task 1: Desktop uptime accumulator

**Files:**
- Create: `desktop-app/src/system_info/uptime.py`
- Modify: `desktop-app/src/system_info/cli.py`
- Modify: `desktop-app/tests/test_system_info.py`

**Interfaces:**
- Produces: `collect_uptime(now: float | None = None, boot_time: float | None = None, state_path: Path | None = None) -> UptimeInfo`
- Produces: `UptimeInfo.to_dict()` → `{boot_time, uptime_seconds, by_day, day_timezone: "UTC"}`

- [ ] Tests for midnight UTC split + reboot (no credit while off)
- [ ] Implement accumulator + 90-day prune; state at `user_config_dir()/uptime.json`
- [ ] Wire into CLI full/`--sys` report + text output
- [ ] `cd desktop-app && uv run pytest`

### Task 2: Desktop download Mbps probe

**Files:**
- Modify: `desktop-app/src/system_info/network.py`
- Modify: `desktop-app/src/system_info/cli.py`
- Modify: `desktop-app/tests/test_system_info.py`

**Interfaces:**
- Extends `NetworkUsage.to_dict()` with `download_mbps: float | None`, `upload_mbps: null`
- Produces: timed GET of a small public object (e.g. Cloudflare `speed.cloudflare.com/__down?bytes=1000000`), timeout ~8s

- [ ] Test Mbps calc with mocked response stream
- [ ] Implement probe; keep NIC totals/rates
- [ ] Print Mbps in CLI network section
- [ ] `cd desktop-app && uv run pytest`

### Task 3: API optional `uptime`

**Files:**
- Modify: `api/src/sysinfo_api/models.py`
- Modify: `api/tests/test_api.py` (if create-report coverage exists)

- [ ] Add `uptime: dict | None = None` on `Report`
- [ ] `cd api && uv run pytest`

### Task 4: Admin types + MachineDetail UI

**Files:**
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/components/dashboard/machine-detail.tsx`
- Modify: `CONTEXT.md` (brief)

- [ ] Extend `Report` types for `uptime` + network Mbps fields
- [ ] Helpers: `fmtUptime(seconds)`, `fmtMbps`, `formatUtcDayBd(utcDay)`
- [ ] Uptime section + bandwidth chart + internet speed card
- [ ] `cd dashboard && pnpm build`

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Agent UTC `by_day` | 1 |
| `download_mbps` probe | 2 |
| API optional uptime | 3 |
| BD labels + charts in Fleet/Reports | 4 |

## Execution

Inline in this session (user: go).
