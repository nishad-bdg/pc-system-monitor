from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from .. import db

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> JSONResponse:
    if not db.ping():
        return JSONResponse(status_code=503, content={"status": "degraded", "mongo": False})
    return JSONResponse(content={"status": "ok", "mongo": True})