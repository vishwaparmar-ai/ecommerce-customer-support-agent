from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from backend.db.models import ReturnStatus


class ReturnRequest(BaseModel):
    order_id: UUID
    reason: str


class ReturnResponse(BaseModel):
    id: UUID
    order_id: UUID
    customer_id: UUID
    reason: str
    status: ReturnStatus
    requested_at: datetime
    approved_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True