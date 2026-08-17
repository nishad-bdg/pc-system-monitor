import csv
import io
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from .. import db, realtime, security
from ..models import Report, ReportOut
from ..security import ApiKey, CurrentUser
from .realtime import annotate_online

router = APIRouter(prefix="/reports", tags=["reports"])


def _machine_keys(report: Report) -> list[str]:
    """Machine identity keys for the report (device_id + pc_name + macs)."""
    keys: list[str] = []
    if report.device_id:
        keys.append(f"id:{report.device_id}")
    if report.pc_name:
        keys.append(f"name:{report.pc_name}")
    if report.mac_address:
        keys.append(f"mac:{report.mac_address}")
    return keys


@router.post("", status_code=201, response_model=ReportOut)
async def create_report(report: Report, api_key: ApiKey) -> JSONResponse:
    document = report.model_dump(exclude_none=True)
    document["created_at"] = report.created_at or time.time()
    document["source_key"] = api_key["prefix"]
    report_id = db.save_report(document)
    if report_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    # A key linked to a group auto-assigns the PC to that group (one bucket).
    group_id = api_key.get("group_id")
    if group_id:
        db.assign_machine_keys_to_group(group_id, _machine_keys(report))
    # Annotate online state and push to connected dashboards (incl. printers).
    annotate_online(document)
    if report.device_id:
        db.touch_machine(report.device_id, report.pc_name, seen_at=document["created_at"])
    if report.device_id:
        await realtime.broadcast_presence(
            report.device_id,
            online=True,
            last_seen=document["created_at"],
            pc_name=report.pc_name,
        )
    await realtime.broadcast(document)
    return JSONResponse(status_code=201, content={"id": str(report_id)})


def _user_group_ids(user: dict) -> list[str] | None:
    """Group ids to scope a non-super-admin request to, or None (no restriction)."""
    if user.get("role") == security.ROLE_SUPER_ADMIN:
        return None
    return user.get("groups") or []


@router.get("")
def get_reports(
    limit: int = 20,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    country: str | None = None,
    os: str | None = None,
    group_id: str | None = None,
    sub_category_id: str | None = None,
    disk_health: str | None = None,
    battery: str | None = None,
    battery_health_min: float | None = None,
    user: CurrentUser = None,
) -> dict:
    records = db.list_reports(
        min(max(limit, 1), 500),
        device_id=device_id or None,
        pc_name=pc_name or None,
        from_ts=from_ts,
        to_ts=to_ts,
        country=country or None,
        os_name=os or None,
        group_id=group_id or None,
        group_ids=_user_group_ids(user),
        sub_category_id=sub_category_id or None,
        disk_health=disk_health or None,
        battery=battery or None,
        battery_health_min=battery_health_min,
    )
    seen_map = db.machines_seen_map()
    for rec in records:
        annotate_online(rec, seen_map)
    return {"total": len(records), "reports": records}


@router.get("/export")
def export_reports_csv(
    limit: int = 10000,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    country: str | None = None,
    os: str | None = None,
    group_id: str | None = None,
    sub_category_id: str | None = None,
    disk_health: str | None = None,
    battery: str | None = None,
    battery_health_min: float | None = None,
    user: CurrentUser = None,
) -> StreamingResponse:
    records = db.list_reports(
        min(max(limit, 1), 10000),
        device_id=device_id or None,
        pc_name=pc_name or None,
        from_ts=from_ts,
        to_ts=to_ts,
        country=country or None,
        os_name=os or None,
        group_id=group_id or None,
        group_ids=_user_group_ids(user),
        sub_category_id=sub_category_id or None,
        disk_health=disk_health or None,
        battery=battery or None,
        battery_health_min=battery_health_min,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    rows = [flatten_report(enrich_summary(r)) for r in records]
    columns = _column_order(rows)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_cell(row.get(col)) for col in columns])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reports.csv"',
        },
    )


def _report_belongs_to_groups(report: dict, group_ids: list[str]) -> bool:
    """True if a report's machine identity matches any key in the given groups.

    Also expands to sub-categories linked to those groups (a sub-category can
    belong to several groups, many-to-many).
    """
    if not group_ids:
        return False
    groups = [g for g in db.list_groups() if g["_id"] in set(group_ids)]
    if not groups:
        return False
    allowed_keys: set[str] = set()
    for g in groups:
        allowed_keys.update(g.get("machine_keys") or [])
        linked_sub_ids = g.get("subcategory_ids") or []
        for sub in db.list_sub_categories():
            if sub["_id"] in linked_sub_ids:
                allowed_keys.update(sub.get("machine_keys") or [])

    device = report.get("device_id")
    name = (report.get("pc_name") or "").lower()
    hostname = ((report.get("os") or {}).get("hostname") or "").lower()
    macs = [report.get("mac_address") or ""] + [
        i.get("mac") or "" for i in (report.get("mac_addresses") or [])
    ]
    for key in allowed_keys:
        if key.startswith("id:") and device and key[3:] == device:
            return True
        if key.startswith("name:"):
            needle = key[5:].lower()
            if needle and (needle == name or needle == hostname):
                return True
        if key.startswith("mac:"):
            needle = key[3:].lower().replace("-", "").replace(":", "")
            for m in macs:
                if m.lower().replace("-", "").replace(":", "") == needle:
                    return True
    return False


@router.get("/{report_id}")
def get_report(report_id: str, user: CurrentUser = None) -> dict:
    doc = db.get_report(report_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if user.get("role") != security.ROLE_SUPER_ADMIN and not _report_belongs_to_groups(
        doc, user.get("groups") or []
    ):
        raise HTTPException(status_code=403, detail="Report is outside your groups")
    annotate_online(doc)
    return doc


# ---- CSV flattening ----

# Field order for CSV columns: top-level and the most useful nested values first,
# then everything else discovered in reports gets appended.
_CSV_COLUMN_PREFIXES = (
    "created_at",
    "pc_name",
    "device_id",
    "source_key",
    "os.system",
    "os.release",
    "os.machine",
    "os.hostname",
    "os.windows_activation.",
    "private_ip",
    "public_ip",
    "mac_address",
    "location.",
    "resources.cpu_count",
    "resources.cpu_count_physical",
    "resources.cpu_percent",
    "resources.cpu_freq_mhz",
    "resources.cpu_brand",
    "resources.cpu_name",
    "resources.ram_total",
    "resources.ram_used",
    "resources.ram_available",
    "resources.ram_free",
    "resources.ram_percent",
    "resources.ram_speed_mhz",
    "resources.ram_type",
    "resources.swap_total",
    "resources.swap_used",
    "resources.swap_percent",
    "resources.battery.",
    "disk.",
    "printers.",
    "summary.",
    "network.",
    "uptime.",
    "security.",
    "health.",
    "email_accounts.",
    "processes.",
    "mac_addresses.",
)


def _safe(value):
    """Coerce a value we want to sum/compare into a number, else 0."""
    if isinstance(value, (int, float)) and value == value:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _sum_field(items: list | None, field: str) -> float:
    return sum(_safe(item.get(field)) for item in (items or []) if isinstance(item, dict))


def enrich_summary(report: dict) -> dict:
    """Add a `summary.*` block with computed totals for the CSV report.

    Columns included: total uptime (sum of tracked days), network total bytes,
    printer prints, SSD/HDD counts, disk health, and battery health snapshot.
    """
    enriched = dict(report)

    up = report.get("uptime") or {}
    by_day = up.get("by_day") or {}
    uptime_secs = 0
    if isinstance(by_day, dict):
        uptime_secs = int(sum(_safe(v) for v in by_day.values()))
    else:
        uptime_secs = int(_safe(up.get("uptime_seconds")))

    net = report.get("network") or {}
    network_total = int(_safe(net.get("bytes_sent")) + _safe(net.get("bytes_recv")))

    printers = report.get("printers") or {}
    print_total = 0
    for group in ("usb", "network", "other"):
        print_total += int(_sum_field(printers.get(group), "print_count"))
    printer_count = sum(
        len(printers.get(group) or []) for group in ("usb", "network", "other")
    )

    disks = report.get("health", {}) or {}
    disk_list = disks.get("disks") or []
    ssd_count = sum(1 for d in disk_list if isinstance(d, dict) and d.get("media_type") == "ssd")
    hdd_count = sum(1 for d in disk_list if isinstance(d, dict) and d.get("media_type") == "hdd")
    disk_ok = sum(1 for d in disk_list if isinstance(d, dict) and d.get("health") == "ok")
    disk_problems = sum(
        1 for d in disk_list if isinstance(d, dict) and d.get("health") in ("warning", "fail")
    )

    battery = disks.get("battery")
    battery_present = bool(battery)

    disk_percent_used = None
    disk_devices = report.get("disk", {}) or {}
    devs = disk_devices.get("devices") or []
    total_bytes = sum(_safe(d.get("total")) for d in devs if isinstance(d, dict))
    used_bytes = sum(_safe(d.get("used")) for d in devs if isinstance(d, dict))
    if total_bytes > 0:
        disk_percent_used = int(round(used_bytes / total_bytes * 100))

    res = report.get("resources") or {}
    ssd_brands = sorted(
        {str(d.get("brand") or "").strip() for d in disk_list if isinstance(d, dict) and d.get("media_type") == "ssd" and d.get("brand")}
    )
    hdd_brands = sorted(
        {str(d.get("brand") or "").strip() for d in disk_list if isinstance(d, dict) and d.get("media_type") == "hdd" and d.get("brand")}
    )

    enriched["summary"] = {
        "total_uptime_seconds": uptime_secs,
        "total_uptime_days": round(uptime_secs / 86400, 2),
        "network_total_bytes": network_total,
        "print_count_total": print_total,
        "printer_count": printer_count,
        "cpu_brand": res.get("cpu_brand"),
        "cpu_name": res.get("cpu_name"),
        "ssd_count": ssd_count,
        "hdd_count": hdd_count,
        "ssd_brands": "; ".join(ssd_brands) or None,
        "hdd_brands": "; ".join(hdd_brands) or None,
        "disk_healthy_count": disk_ok,
        "disk_problem_count": disk_problems,
        "disk_percent_used": disk_percent_used,
        "battery_present": battery_present,
        "battery_health_percent": battery.get("health_percent") if isinstance(battery, dict) else None,
        "battery_cycle_count": battery.get("cycle_count") if isinstance(battery, dict) else None,
        "battery_condition": battery.get("condition") if isinstance(battery, dict) else None,
    }
    return enriched


def flatten_report(report: dict, prefix: str = "") -> dict:
    """Flatten a report into { 'a.b.c': value } scalar cells (arrays -> JSON)."""
    flat: dict = {}
    for key, value in report.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_report(value, f"{dotted}."))
        elif isinstance(value, list):
            flat[dotted] = value
        else:
            flat[dotted] = value
    return flat


def _column_order(rows: list[dict]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for col in row:
            if col not in seen:
                seen.append(col)
    seen.sort(key=_column_rank)
    return seen


def _column_rank(col: str) -> int:
    for rank, prefix in enumerate(_CSV_COLUMN_PREFIXES):
        if col == prefix.rstrip(".") or col.startswith(prefix):
            return rank
    return len(_CSV_COLUMN_PREFIXES)


def _csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        import json

        return json.dumps(value)
    return str(value)
