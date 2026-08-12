from pydantic import BaseModel, Field


class Report(BaseModel):
    os: dict = {}
    private_ip: str | None = None
    public_ip: str | None = None
    mac_address: str | None = None
    mac_addresses: list[dict] = []
    location: dict | None = None
    resources: dict | None = None
    disk: dict | None = None
    created_at: float | None = Field(default=None, description="Unix timestamp")


class ReportOut(BaseModel):
    id: str