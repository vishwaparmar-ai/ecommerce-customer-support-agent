from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from backend.db.models import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM
    order_id: UUID | None = None


class TicketStatusUpdate(BaseModel):
    new_status: TicketStatus
    changed_by: str


class TicketAssign(BaseModel):
    assigned_to: str
    changed_by: str


class TicketResponse(BaseModel):
    id: UUID
    customer_id: UUID
    order_id: UUID | None = None
    subject: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    assigned_to: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True