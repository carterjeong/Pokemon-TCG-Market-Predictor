"""Health-check response schemas (Pydantic V2)."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str
    version: str


class DBHealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["reachable", "unreachable"]
