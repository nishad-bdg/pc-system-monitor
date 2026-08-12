from pydantic import BaseModel

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db, security

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    active: bool


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(user: security.CurrentUser) -> list:
    return db.list_api_keys()


@router.post("", status_code=201)
def create_api_key(payload: ApiKeyCreate, user: security.CurrentUser) -> JSONResponse:
    key = security.generate_api_key()
    key_id = db.create_api_key(payload.name, security.hash_api_key(key), key[:20])
    if key_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return JSONResponse(
        status_code=201,
        content={"id": str(key_id), "name": payload.name, "api_key": key},
    )


@router.delete("/{key_id}", status_code=204)
def delete_api_key(key_id: str, user: security.CurrentUser) -> None:
    if db.delete_api_key(key_id):
        return None
    raise HTTPException(status_code=404, detail="API key not found")