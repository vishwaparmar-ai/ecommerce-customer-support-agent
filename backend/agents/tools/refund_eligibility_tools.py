"""
Agent tools: refund eligibility (read-only, by design).

This is deliberately NOT a "create_refund" tool. The agent should never be
the thing that marks a refund COMPLETED or moves a payment to REFUNDED --
even in mock/simulated form. This tool only validates eligibility (same
checks refund_service.process_refund runs before it executes) and returns
a canned, policy-based reassurance message. It creates nothing and
executes nothing.

Actual refund execution (refund_service.process_refund) stays a separate,
non-agent-exposed service function -- called by an internal/admin process,
never by this tool. If you want a real execution path, that belongs behind
staff auth on the REST API, not behind an LLM's tool call.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import Customer, PaymentStatus, Refund, ReturnStatus
from backend.services.order_service import get_order_for_customer

REFUND_TIMELINE_MESSAGE = "Your refund will be credited within 5-7 business days."


class CheckRefundEligibilityInput(BaseModel):
    order_id: uuid.UUID = Field(description="The UUID of the order to check refund eligibility for")


def make_check_refund_eligibility_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a check_refund_eligibility tool scoped to current_user.
    Read-only: validates ownership, that a return exists and is COMPLETED,
    that the payment was actually PAID, and that no refund already exists --
    then returns a message. Never creates a Refund row, never changes
    Payment.status. Mirrors the validation in refund_service.process_refund
    without the side effects.
    """

    def _check_refund_eligibility(order_id: uuid.UUID) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
        except Exception as exc:
            return {"error": str(getattr(exc, "detail", exc))}

        if not order.returns:
            return {
                "eligible": False,
                "reason": "No return has been requested for this order yet, so there's nothing to refund.",
            }

        ret = order.returns[0]

        if ret.status != ReturnStatus.COMPLETED:
            return {
                "eligible": False,
                "reason": f"The return for this order is currently '{ret.status.value}', "
                          f"not yet completed -- a refund can only be issued once the "
                          f"return is fully processed.",
            }

        payment = order.payment
        if payment is None or payment.status != PaymentStatus.PAID:
            return {
                "eligible": False,
                "reason": "No successful payment was found for this order to refund.",
            }

        existing_refund = db.query(Refund).filter(Refund.return_id == ret.id).first()
        if existing_refund is not None:
            return {
                "eligible": False,
                "reason": f"A refund has already been issued for this order "
                          f"(status: {existing_refund.status.value}).",
            }

        logger.info(
            "tool_check_refund_eligibility_eligible",
            extra={"customer_id": str(current_user.id), "order_id": str(order_id)},
        )
        return {
            "eligible": True,
            "message": REFUND_TIMELINE_MESSAGE,
        }

    return StructuredTool.from_function(
        func=_check_refund_eligibility,
        name="check_refund_eligibility",
        description=(
            "Check whether the current customer's order is eligible for a "
            "refund and, if so, return the standard timeline message to "
            "tell them. This NEVER issues a refund or changes any payment "
            "record -- it only checks eligibility and informs the customer. "
            "Use this when a customer asks for a refund; do not claim a "
            "refund has been processed or that money has moved."
        ),
        args_schema=CheckRefundEligibilityInput,
    )