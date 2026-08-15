# Sub-categories design

Date: 2026-08-15

## Objective

Allow refining a group into **sub-categories** (e.g. floors, labs, sites) while keeping machine grouping simple and unambiguous.

## Context

Groups currently hold an exclusive set of `machine_keys` — a PC belongs to exactly one group. Users want finer buckets than a flat group list, but a sub-category is not a parent/child tree: the same sub-category should be reusable across groups (e.g. "Floor 3" belongs to Operations **and** Facilities).

## Model

Shared `sub_categories` Mongo collection. Many-to-many group linkage:

- Group doc: `subcategory_ids: string[]`
- Sub-category doc: `{ _id, name, group_ids: string[], machine_keys: string[], created_at }`

**One-bucket exclusivity (unchanged rule, now across buckets):** a PC lives in its main group **or** one sub-category, never both. Assigning a machine key anywhere removes it from:

- every other group (`remove_machine_keys_from_groups`), and
- every other sub-category (`remove_machine_keys_from_sub_categories`).

A sub-category must always be linked to at least one group to be visible/usable, but is not a tree: it has no single parent.

## Group membership semantics

- `GET /reports` / `/reports/export` / `/reports/{id}` scoped by a group **also include** machines in that group's linked sub-categories. This is why `group_machine_keys` / `_group_filter` expand:
  1. the group's own `machine_keys`, **plus**
  2. `machine_keys` of every sub-category referenced by `group.subcategory_ids`.

  A sub-category linked to N groups therefore shows its PCs under **all** N parent groups. `GET /groups` includes `subcategory_ids`; `GET /sub-categories` includes `group_ids` + `machine_keys`.

- New explicit filter `sub_category_id` (reports + export) matches only that sub-category's machines. `GET /sub-categories` returns all for admin/super_admin, and only sub-categories linked to the caller's groups for the `user` role.

## API

- `GET/POST/PATCH/DELETE /sub-categories` (admin/super_admin for writes; `user` reads only their own groups' sub-categories).
  - `POST { name, group_ids }` → creates and back-links `group.subcategory_ids`.
  - `PATCH { name?, group_ids?, machine_keys? }` → updating `machine_keys` enforces one-bucket; updating `group_ids` re-syncs `group.subcategory_ids` (detach then re-attach).
  - `DELETE` → detaches from all groups and removes the doc.

## Dashboard (Groups page, per-group panel)

- Each selected group lists its linked sub-categories with PC counts, group chips, a PC picker (one-bucket), and delete.
- "+ New sub-category" modal: name + multi-select of groups (current group pre-selected).
- PC assign table gains a "Sub-category" column (options = sub-categories of the selected group); the sidebar footer shows sub-category counts.
- Reports browser + Report export gain a "Sub-category" filter (scoped to sub-categories of the selected group, if a group is chosen).

## Tests

API: list (admin + user-role scoping), create (incl. blank name), update assigns keys (one-bucket exclusivity), delete, reports `sub_category_id` filter, `_group_filter` expands to a sub-category's machines, and invalid sub-category/group ids return 200 with empty results (no 500).

## Verification

```bash
cd api && uv run pytest -q        # 83 passed
cd desktop-app && uv run pytest -q  # 54 passed
cd dashboard && pnpm build         # green
```