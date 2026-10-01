from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user, require_role
from backend.db.models import Customer, CustomerRole
from backend.schemas.support import (
    TicketAssign,
    TicketCreate,
    TicketResponse,
    TicketStatusUpdate,
)
from backend.services.support_service import (
    assign_ticket,
    create_ticket,
    get_ticket_for_customer,
    list_tickets_for_customer,
    update_ticket_status,
)

router = APIRouter(
    prefix="/support",
    tags=["Support"],
)


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_new_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Create a support ticket for an issue or order."""
    ticket = create_ticket(
        db=db,
        current_user=current_user,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
        order_id=payload.order_id,
    )
    return ticket


@router.get("/tickets", response_model=list[TicketResponse])
@router.get("/", response_model=list[TicketResponse])
def list_tickets(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """List tickets for the current customer (or all tickets for staff/admin)."""
    return list_tickets_for_customer(
        db=db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Retrieve details of a support ticket."""
    return get_ticket_for_customer(
        db=db,
        ticket_id=ticket_id,
        current_user=current_user,
    )


@router.patch("/tickets/{ticket_id}/status", response_model=TicketResponse)
def change_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    """Staff/Admin only: update the status of a ticket."""
    return update_ticket_status(
        db=db,
        ticket_id=ticket_id,
        new_status=payload.new_status,
        changed_by=current_staff.email,
    )


@router.patch("/tickets/{ticket_id}/assign", response_model=TicketResponse)
def assign_ticket_to_agent(
    ticket_id: uuid.UUID,
    payload: TicketAssign,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    """Staff/Admin only: assign a ticket to an agent."""
    return assign_ticket(
        db=db,
        ticket_id=ticket_id,
        assigned_to=payload.assigned_to,
        changed_by=current_staff.email,
    )