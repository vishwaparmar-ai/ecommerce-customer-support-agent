"""
Support ticket endpoints.

NOTE on schemas: I haven't seen your schemas/ folder, so TicketCreate /
TicketStatusUpdate / TicketAssign below are placeholders showing the shape
each endpoint expects. If you already have (or create) matching Pydantic
schemas under backend/schemas/, swap the inline classes for real imports
from there instead.

AUTHORIZATION (Phase 7): update_status and assign are now gated behind
require_role(SUPPORT_STAFF, ADMIN) instead of plain get_current_user --
closing the gap flagged when these were first built. create_new_ticket
stays customer-facing (any logged-in customer can file their own ticket),
since filing one isn't a staff-only action.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user, require_role
from backend.db.models import Customer, CustomerRole
from backend.services.support_service import (
    create_ticket,
    update_ticket_status,
    assign_ticket,
)

from backend.schemas.support import TicketAssign,TicketCreate,TicketStatusUpdate

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


@router.patch("/{ticket_id}/status", status_code=status.HTTP_200_OK)
def change_ticket_status(
    ticket_id: UUID,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    ticket = update_ticket_status(
        db=db,
        ticket_id=ticket_id,
        new_status=payload.new_status,
        changed_by=current_staff.email,
    )

    return {
        "message": "Ticket status updated",
        "ticket_id": ticket.id,
        "status": ticket.status.value,
    }



@router.patch("/{ticket_id}/assign", status_code=status.HTTP_200_OK)
def assign_ticket_to_agent(
    ticket_id: UUID,
    payload: TicketAssign,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    ticket = assign_ticket(
        db=db,
        ticket_id=ticket_id,
        assigned_to=payload.assigned_to,
        changed_by=current_staff.email,
    )

    return {
        "message": "Ticket assigned",
        "ticket_id": ticket.id,
        "assigned_to": ticket.assigned_to,
        "status": ticket.status.value,
    }