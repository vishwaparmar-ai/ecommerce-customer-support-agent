"""
Agent tools: human escalation (write).

Distinct from create_support_ticket: this is for handing a case to a
human RIGHT NOW, not logging something for later review. Per the doc's
escalation triggers (section 14): explicit request for a human, low
confidence / conflicting evidence, fraud or security concerns, high-value
or unusual situations, policy ambiguity, repeated failures, or a
consequential tool failure.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import Customer, TicketPriority
from backend.services.support_service import create_ticket


class EscalateToHumanInput(BaseModel):
    reason: str = Field(
        description=(
            "Why this needs a human right now -- e.g. 'customer explicitly "
            "requested a human', 'possible fraud/account security concern', "
            "'ambiguous situation not covered by policy', 'repeated failed "
            "resolution attempts'"
        )
    )
    summary: str = Field(
        description=(
            "A concise summary of the conversation so far and what's been "
            "tried, written for the human agent picking this up -- what "
            "the customer wants, what tools were already called, and why "
            "you couldn't resolve it yourself"
        )
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        description="The order this relates to, if any",
    )


def make_escalate_to_human_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds an escalate_to_human tool scoped to current_user. Currently
    implemented as a CRITICAL-priority support ticket -- there's no
    separate "escalation" concept in the schema yet, so priority is what
    signals urgency to whoever triages tickets. Revisit this once there's
    a real staff-facing queue that can distinguish "escalated, needs
    immediate attention" from "just a critical ticket".
    """

    def _escalate_to_human(reason: str, summary: str, order_id: uuid.UUID | None = None) -> dict:
        try:
            ticket = create_ticket(
                db=db,
                current_user=current_user,
                subject=f"Escalation: {reason}"[:255],
                description=summary,
                priority=TicketPriority.CRITICAL,
                order_id=order_id,
            )
            logger.info(
                "tool_escalate_to_human_success",
                extra={
                    "customer_id": str(current_user.id),
                    "ticket_id": str(ticket.id),
                    "reason": reason,
                },
            )
            return {
                "escalated": True,
                "ticket_id": str(ticket.id),
                "message": "This has been escalated to a human agent who will follow up shortly.",
            }
        except Exception as exc:
            logger.info(
                "tool_escalate_to_human_failed",
                extra={"customer_id": str(current_user.id), "error": str(exc)},
            )
            return {"escalated": False, "error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_escalate_to_human,
        name="escalate_to_human",
        description=(
            "Immediately hand this conversation off to a human agent. Use "
            "this when: the customer explicitly asks for a human; you're "
            "not confident in the correct answer or the evidence conflicts; "
            "there's any hint of fraud or account security risk; the "
            "situation involves an unusual or high-value request; the "
            "policy is ambiguous for this case; you've already tried and "
            "failed to resolve this; or a tool call failed in a way that "
            "left things inconsistent. This is for handing off NOW -- use "
            "create_support_ticket instead for issues that just need to be "
            "logged for later, non-urgent review."
        ),
        args_schema=EscalateToHumanInput,
    )