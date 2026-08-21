"""
Support service.

Encapsulates support ticket business logic so routers stay thin:
    - create_ticket: validates the linked order (if any) belongs to the
      customer, creates the ticket in OPEN state, and logs creation.
    - update_ticket_status: validates the transition is allowed, then
      updates status and logs the change (old -> new).
    - assign_ticket: assigns/reassigns a ticket to a support agent and
      logs the change.

Since SupportTicket only stores current state (no history table), every
mutation here is logged via core.logging so there's an auditable trail of
who changed what and when, even without a dedicated audit table.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import logging
from db.models import (
    Customer,
    Order,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)

logger = logging.getLogger(__name__)


# Allowed forward transitions. A ticket can only move to one of the states
# listed for its current status; anything else is rejected. RESOLVED and
# CLOSED tickets can be reopened back to IN_PROGRESS if the customer
# responds with a new issue on the same ticket.
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.WAITING_CUSTOMER: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.RESOLVED: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.CLOSED: {TicketStatus.IN_PROGRESS},
}


# Create ticket

def create_ticket(
    db: Session,
    current_user: Customer,
    subject: str,
    description: str,
    priority: TicketPriority = TicketPriority.MEDIUM,
    order_id: uuid.UUID | None = None,
) -> SupportTicket:
    """
    Validates the linked order (if provided) belongs to the current
    customer, then creates the ticket in OPEN state. Logs creation for
    auditability.
    """
    if not subject or not subject.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject is required")
    if not description or not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Description is required")

    if order_id is not None:
        order = db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        if order.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this order",
            )

    try:
        ticket = SupportTicket(
            id=uuid.uuid4(),
            customer_id=current_user.id,
            order_id=order_id,
            subject=subject.strip(),
            description=description.strip(),
            priority=priority,
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        logger.info(
            "ticket_created",
            extra={
                "ticket_id": str(ticket.id),
                "customer_id": str(current_user.id),
                "order_id": str(order_id) if order_id else None,
                "priority": priority.value,
            },
        )
        return ticket

    except Exception:
        db.rollback()
        logger.exception("ticket_creation_failed", extra={"customer_id": str(current_user.id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create support ticket",
        )


# Update ticket status

def update_ticket_status(
    db: Session,
    ticket_id: uuid.UUID,
    new_status: TicketStatus,
    changed_by: str,
) -> SupportTicket:
    """
    Validates the requested status transition is allowed from the ticket's
    current status, applies it, and logs the change (old -> new, by whom)
    for auditability.

    changed_by: identifier of whoever made the change (agent name/email,
    or "customer" / "system" for automated transitions). Required so the
    log entry is actually attributable, per the "auditable" requirement.
    """
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    old_status = ticket.status
    if new_status == old_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticket is already in status '{old_status.value}'",
        )

    allowed = ALLOWED_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move ticket from '{old_status.value}' to '{new_status.value}'",
        )

    try:
        ticket.status = new_status
        db.commit()
        db.refresh(ticket)

        logger.info(
            "ticket_status_changed",
            extra={
                "ticket_id": str(ticket.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
                "changed_by": changed_by,
            },
        )
        return ticket

    except Exception:
        db.rollback()
        logger.exception("ticket_status_update_failed", extra={"ticket_id": str(ticket_id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket status",
        )


# Assign ticket

def assign_ticket(db: Session, ticket_id: uuid.UUID, assigned_to: str, changed_by: str) -> SupportTicket:
    """
    Assigns (or reassigns) a ticket to a support agent. Logs the previous
    and new assignee for auditability.
    """
    if not assigned_to or not assigned_to.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assigned_to is required")

    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    try:
        previous_assignee = ticket.assigned_to
        ticket.assigned_to = assigned_to.strip()

        # A ticket picked up by an agent naturally moves out of OPEN.
        if ticket.status == TicketStatus.OPEN:
            ticket.status = TicketStatus.IN_PROGRESS

        db.commit()
        db.refresh(ticket)

        logger.info(
            "ticket_assigned",
            extra={
                "ticket_id": str(ticket.id),
                "previous_assignee": previous_assignee,
                "new_assignee": ticket.assigned_to,
                "changed_by": changed_by,
            },
        )
        return ticket

    except Exception:
        db.rollback()
        logger.exception("ticket_assignment_failed", extra={"ticket_id": str(ticket_id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign ticket",
        )