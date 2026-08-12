# Multi-PC Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach `pc_name` + `device_id` from the desktop app, filter reports in the API, and ship a slate+blue sidebar admin UI for multi-PC fleets.

**Architecture:** Reports remain the source of truth. Desktop resolves platform-specific names and posts identity fields; API stores and filters them; dashboard groups by `device_id` into a sidebar list with per-machine charts.

**Tech Stack:** Python CLI (`system_info`), FastAPI + MongoDB, Next.js dashboard (NextAuth, TanStack Query, Recharts, Tailwind).

## Global Constraints

- macOS: `pc_name` always from hostname (ignore custom override).
- Windows: `--pc-name` / `SYSTEM_INFO_PC_NAME`, else hostname.
- No separate machines collection.
- Admin UI: Layout B + slate/blue (no purple/glow theme).
- Do not commit unless the user asks.

---

### Task 1: Desktop PC identity

**Files:**
- Modify: `desktop-app/src/system_info/device.py`
- Modify: `desktop-app/src/system_info/cli.py`
- Modify: `desktop-app/tests/test_system_info.py`

**Interfaces:**
- Produces: `resolve_pc_name(explicit: str | None = None) -> str`
- Produces: report payload keys `pc_name`, `device_id`

- [ ] Add `resolve_pc_name` + tests (Darwin vs Windows)
- [ ] Wire CLI `--pc-name` / env into report POST + output
- [ ] Run `cd desktop-app && uv run pytest`

### Task 2: API identity fields + filters

**Files:**
- Modify: `api/src/sysinfo_api/models.py`
- Modify: `api/src/sysinfo_api/db.py`
- Modify: `api/src/sysinfo_api/routes/reports.py`
- Modify: `api/tests/test_api.py`

**Interfaces:**
- Produces: `list_reports(limit, device_id=None, pc_name=None) -> list[dict]`
- Produces: `Report.pc_name`, `Report.device_id`

- [ ] Extend model + DB filters + route query params
- [ ] Tests for create with identity + filtered list
- [ ] Run `cd api && uv run pytest`

### Task 3: Admin dashboard slate+blue fleet UI

**Files:**
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/components/dashboard/dashboard.tsx`
- Modify: `dashboard/src/components/dashboard/sign-out-button.tsx`
- Modify: `dashboard/src/app/globals.css`
- Modify: `dashboard/src/app/layout.tsx`
- Modify: `dashboard/src/app/login/page.tsx`
- Modify: `dashboard/README.md` / root `README.md` if CLI flags documented

- [ ] Types + fleet grouping helpers
- [ ] Sidebar list + filter + detail pane UI
- [ ] Run `cd dashboard && pnpm build`

---

## Execution

Inline execution in this session (user requested implement).
