"""
Agent tools: support tickets (write).

Wraps support ticket creation as a typed LangChain tool. Plain "Write"
tool per the tool table -- creating a ticket isn't a high-impact action
(no money moves, nothing irreversible), so no approval gate needed.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.db.models import Customer, TicketPriority
from backend.services.support_service import create_ticket


class CreateSupportTicketInput(BaseModel):
    subject: str = Field(description="A short summary of the issue, a few words")
    description: str = Field(description="The full issue in the customer's own words, with any relevant details")
    priority: TicketPriority = Field(
        default=TicketPriority.MEDIUM,
        description=(
            "How urgent this is. low: general questions, minor issues. "
            "medium: standard order/return/refund issues. high: payment "
            "discrepancies, repeated failed deliveries, time-sensitive "
            "complaints. critical: fraud, account security, safety issues."
        ),
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        description="The order this ticket relates to, if any -- omit if the issue isn't about a specific order",
    )


def make_create_support_ticket_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a create_support_ticket tool scoped to current_user.
    create_ticket already validates order ownership internally if
    order_id is given, so this tool inherits that check for free.
    """

    def _create_support_ticket(
        subject: str,
        description: str,
        priority: TicketPriority = TicketPriority.MEDIUM,
        order_id: uuid.UUID | None = None,
    ) -> dict:
        try:
            ticket = create_ticket(
                db=db,
                current_user=current_user,
                subject=subject,
                description=description,
                priority=priority,
                order_id=order_id,
            )
           
            return {
                "created": True,
                "ticket_id": str(ticket.id),
                "status": ticket.status.value,
                "priority": ticket.priority.value,
            }
        except Exception as exc:
          
            return {"created": False, "error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_create_support_ticket,
        name="create_support_ticket",
        description=(
            "Create a support ticket for the current customer for issues "
            "that can't be resolved with the other tools available -- e.g. "
            "something the knowledge base and order/return/refund tools "
            "couldn't answer, or a request the customer explicitly wants "
            "logged for a human to review. Do not use this for a simple "
            "request to speak to a human right now -- use escalate_to_human "
            "for that instead."
        ),
        args_schema=CreateSupportTicketInput,
    )