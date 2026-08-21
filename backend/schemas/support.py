from pydantic import BaseModel
from db.models import TicketPriority, TicketStatus
from uuid import UUID

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