from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel
from backend.db.models import RefundStatus


class OrderRefund(BaseModel):
    return_id: UUID


class RefundResponse(BaseModel):
    id: UUID
    return_id: UUID
    payment_id: UUID
    amount: Decimal
    status: RefundStatus
    refund_reference: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True