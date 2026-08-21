"""
Support ticket endpoints.

NOTE on schemas: I haven't seen your schemas/ folder, so TicketCreate /
TicketStatusUpdate / TicketAssign below are placeholders showing the shape
each endpoint expects. If you already have (or create) matching Pydantic
schemas under backend/schemas/, swap the inline classes for real imports
from there instead.

NOTE on authorization: update_status and assign are support-agent/admin
actions, not customer actions. There's no staff/admin auth shown in what
you've shared so far, so both currently just require get_current_user
(any logged-in customer) plus a free-text `changed_by` field. Once you
have a staff auth dependency, swap get_current_user for that on these two
routes -- as written, any customer could technically hit them.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from db.models import Customer
from db.dependency import get_db, get_current_user
from schemas.support import TicketAssign,TicketCreate,TicketStatusUpdate
from services.support_service import (
    create_ticket
)

router = APIRouter(
    prefix="/support",
    tags=["Support"],
)



@router.post("/", status_code=status.HTTP_201_CREATED)
def create_new_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    ticket = create_ticket(
        db=db,
        current_user=current_user,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
        order_id=payload.order_id,
    )

    return {
        "message": "Support ticket created successfully",
        "ticket_id": ticket.id,
        "status": ticket.status.value,
    }

