import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db
from ..models import Report, ReportOut
from ..security import ApiKey, CurrentUser

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", status_code=201, response_model=ReportOut)
def create_report(report: Report, api_key: ApiKey) -> JSONResponse:
    document = report.model_dump(exclude_none=True)
    document["created_at"] = report.created_at or time.time()
    document["source_key"] = api_key["prefix"]
    report_id = db.save_report(document)
    if report_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return JSONResponse(status_code=201, content={"id": str(report_id)})


@router.get("")
def get_reports(
    limit: int = 20,
    device_id: str | None = None,
    pc_name: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    country: str | None = None,
    os: str | None = None,
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
    )
    return {"total": len(records), "reports": records}


@router.get("/{report_id}")
def get_report(report_id: str, user: CurrentUser = None) -> dict:
    doc = db.get_report(report_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return doc
