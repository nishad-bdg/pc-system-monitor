from pydantic import BaseModel

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db, security

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    active: bool
    created_at: float | None = None


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(user: security.SuperAdminUser) -> list[dict]:
    return [
        {
            "id": k["_id"],
            "name": k["name"],
            "prefix": k["prefix"],
            "active": k["active"],
            "created_at": k.get("created_at"),
        }
        for k in db.list_api_keys()
    ]


@router.post("", status_code=201)
def create_api_key(payload: ApiKeyCreate, user: security.SuperAdminUser) -> JSONResponse:
    key = security.generate_api_key()
    key_id = db.create_api_key(payload.name, security.hash_api_key(key), key[:20])
    if key_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return JSONResponse(
        status_code=201,
        content={"id": str(key_id), "name": payload.name, "api_key": key},
    )


@router.delete("/{key_id}", status_code=204)
def delete_api_key(key_id: str, user: security.SuperAdminUser) -> None:
    if db.delete_api_key(key_id):
        return None
    raise HTTPException(status_code=404, detail="API key not found")


@router.patch("/{key_id}", response_model=ApiKeyOut)
def update_api_key(
    key_id: str, payload: ApiKeyUpdate, user: security.SuperAdminUser
) -> dict:
    if not db.update_api_key(key_id, name=payload.name, active=payload.active):
        raise HTTPException(status_code=404, detail="API key not found")
    for key in db.list_api_keys():
        if key["_id"] == key_id:
            return {
                "id": key["_id"],
                "name": key["name"],
                "prefix": key["prefix"],
                "active": key["active"],
                "created_at": key.get("created_at"),
            }
    raise HTTPException(status_code=404, detail="API key not found")


@router.post("/{key_id}/regenerate")
def regenerate_api_key(
    key_id: str, user: security.SuperAdminUser
) -> JSONResponse:
    """Rotate an API key's secret, returning the new key exactly once.

    The previous secret stops working immediately — desktop PCs must be
    updated to use the new key.
    """
    key = security.generate_api_key()
    if not db.update_api_key(
        key_id, key_hash=security.hash_api_key(key), prefix=key[:20]
    ):
        raise HTTPException(status_code=404, detail="API key not found")
    for record in db.list_api_keys():
        if record["_id"] == key_id:
            return JSONResponse(
                content={
                    "id": str(record["_id"]),
                    "name": record["name"],
                    "api_key": key,
                }
            )
    raise HTTPException(status_code=404, detail="API key not found")