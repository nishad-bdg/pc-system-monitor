# Multi-PC monitoring + admin UI polish

## Goal

Support the desktop app on many machines by attaching stable PC identity to each report, filter reports by PC in the API, and rebuild the admin dashboard as a slate+blue sidebar fleet list with per-machine detail.

## Decisions

- **PC naming:** macOS always uses OS hostname. Windows uses `--pc-name` / `SYSTEM_INFO_PC_NAME`, then falls back to hostname if missing/empty.
- **Identity:** Every report includes `pc_name` + stable `device_id` (existing `device.py` helpers).
- **API approach:** Enrich report documents only (no machines collection). Optional `GET /reports` filters: `device_id` (exact), `pc_name` (case-insensitive contains).
- **Admin layout:** Sidebar PC list + detail pane (Layout B).
- **Visual direction:** Slate + blue (dark ink sidebar, light detail, blue selection).

## Desktop

- Resolve `pc_name` via platform rules; always attach `device_id` from `get_or_create_device_id()`.
- Persist `pc_name` alongside `device_id` in `device.json` when writing config.
- Include both fields in POST `/reports` body and in CLI JSON/text output.
- Add `--pc-name` CLI flag (default from `SYSTEM_INFO_PC_NAME`).

## API

- Extend `Report` model with optional `pc_name` and `device_id`.
- Update `list_reports` to accept optional filters and apply them in Mongo queries.
- Existing reports without identity fields remain readable; dashboard falls back to `os.hostname`.

## Dashboard

- Group reports into a fleet list by `device_id`, else `pc_name`, else `os.hostname`.
- Sidebar: search/filter by name, list latest status per PC, select one.
- Detail: CPU/RAM/swap tiles, charts, report history for selected PC only.
- Align login + global tokens to slate/blue; keep NextAuth + TanStack Query.

## Tests

- Desktop: name resolution for Darwin vs Windows (explicit, empty, missing).
- API: create with identity fields; list filtered by `device_id` / `pc_name`.
- Dashboard: production build / typecheck.
