"""Print-job endpoints.

Desktop agents POST newly completed print jobs (`print.job` is broadcast over
the WebSocket so the dashboard updates live); admin dashboards query recent
jobs and per-hour counts.
"""

import time

from fastapi import APIRouter, HTTPException

from .. import db, realtime, security
from ..models import PrintJobsBatch
from ..security import ApiKey, CurrentUser

router = APIRouter(prefix="/print-jobs", tags=["print-jobs"])


def _user_group_ids(user: dict) -> list[str] | None:
    if user.get("role") != security.ROLE_SUPER_ADMIN:
        return user.get("groups") or []
    return None


@router.post("", status_code=201)
async def create_print_jobs(batch: PrintJobsBatch, api_key: ApiKey) -> dict:
    """Store a batch of completed print jobs for a machine (API key auth)."""
    now = time.time()
    documents: list[dict] = []
    for job in batch.jobs:
        documents.append(
            {
                "device_id": batch.device_id,
                "pc_name": batch.pc_name,
                "printer": job.printer,
                "document": job.document,
                "user": job.user,
                "pages": job.pages,
                "completed_at": job.completed_at,
                "created_at": job.completed_at or now,
                "source_key": api_key["prefix"],
            }
        )
    inserted = db.save_print_jobs(documents)
    if inserted != len(documents):
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    if batch.device_id:
        db.touch_machine(batch.device_id, batch.pc_name, seen_at=now)
    for doc in documents:
        await realtime.broadcast_print_job(doc)
    return {"count": len(documents)}


def _effective_group_ids(user: dict, group_id: str | None) -> list[str] | None:
    """User's group scope, optionally narrowed to one `group_id`."""
    scoped = _user_group_ids(user)
    if group_id:
        if scoped is not None and group_id not in scoped:
            return []
        return [group_id]
    return scoped


@router.get("")
def get_print_jobs(
    limit: int = 50,
    skip: int = 0,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    group_id: str | None = None,
    user: CurrentUser = None,
) -> dict:
    """Recent print jobs (admin JWT). Newest first. `skip` + `limit` paginate;
    `total` is the full match count (not the page size)."""
    group_ids = _effective_group_ids(user, group_id)
    limit = min(max(limit, 1), 500)
    skip = max(skip, 0)
    if group_id and group_ids == []:
        return {"total": 0, "skip": skip, "limit": limit, "jobs": []}
    filters = dict(
        device_id=device_id or None,
        pc_name=pc_name or None,
        from_ts=from_ts,
        to_ts=to_ts,
        group_ids=group_ids,
    )
    total = db.count_print_jobs(**filters)
    records = db.list_print_jobs(limit, skip=skip, **filters)
    return {"total": total, "skip": skip, "limit": limit, "jobs": records}


@router.get("/summary")
def print_jobs_summary(
    hours: int = 24,
    user: CurrentUser = None,
) -> dict:
    """Per-hour print-job counts over the last `hours` hours (oldest first)."""
    counts = db.print_jobs_hourly_counts(
        min(max(hours, 1), 720),
        group_ids=_user_group_ids(user),
    )
    return {"hours": hours, "buckets": counts}