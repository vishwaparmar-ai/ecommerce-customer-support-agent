"""
Agent tools: order cancellation (high-impact).

Unlike the plain write tools, cancel_order is marked "High impact" in the
tool table -- it needs customer confirmation before executing, per the
doc's approval flow (section 14): agent proposes -> customer approves ->
service executes -> audit log -> agent confirms outcome.

INTERIM APPROACH (until Phase 5 builds a real LangGraph approval node):
one tool, gated by a `confirmed` flag in its own input schema.
    - confirmed=False (default): returns a PREVIEW only -- whether the
      order is cancellable and what cancelling would do. Nothing is
      cancelled.
    - confirmed=True: actually executes the cancellation.

The system prompt (wherever this tool is bound to an LLM) must instruct
the model to never set confirmed=True unless the customer has explicitly
said yes, in this conversation, after seeing the preview. This is not as
airtight as a real graph-level approval gate -- a sufficiently adversarial
prompt could still get a model to skip straight to confirmed=True. Phase 5
should replace this with a proper interrupt/approval node that enforces
the pause structurally rather than relying on prompt instructions alone.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import Customer
from backend.services.order_service import (
    CANCELLABLE_STATES,
    cancel_order as cancel_order_service,
    get_order_for_customer,
)


class CancelOrderInput(BaseModel):
    order_id: uuid.UUID = Field(description="The UUID of the order to cancel")
    confirmed: bool = Field(
        default=False,
        description=(
            "Set to True ONLY after the customer has explicitly confirmed, "
            "in this conversation, that they want to cancel this specific "
            "order -- after being shown what cancelling will do. If False "
            "(the default), this only returns a preview of what would "
            "happen, without cancelling anything. Always call this with "
            "confirmed=False first, show the customer the preview, and "
            "only call again with confirmed=True after they say yes."
        ),
    )


def make_cancel_order_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a cancel_order tool scoped to current_user. Reuses
    get_order_for_customer for ownership and CANCELLABLE_STATES from
    order_service so the "can this even be cancelled" check stays in sync
    with the REST endpoint's own rules.
    """

    def _cancel_order(order_id: uuid.UUID, confirmed: bool = False) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
        except Exception as exc:
            return {"error": str(getattr(exc, "detail", exc))}

        if order.status not in CANCELLABLE_STATES:
            return {
                "cancellable": False,
                "reason": f"This order cannot be cancelled from status '{order.status.value}'.",
            }

        if not confirmed:
            will_refund = order.payment is not None and order.payment.status.value == "paid"
            logger.info(
                "tool_cancel_order_preview",
                extra={"customer_id": str(current_user.id), "order_id": str(order_id)},
            )
            return {
                "cancellable": True,
                "requires_confirmation": True,
                "preview": {
                    "order_id": str(order.id),
                    "current_status": order.status.value,
                    "total_amount": str(order.total_amount),
                    "will_refund": will_refund,
                },
                "message": (
                    "Ask the customer to confirm they want to cancel this "
                    "order before calling this tool again with confirmed=true."
                ),
            }

        try:
            cancelled_order = cancel_order_service(db, current_user, order_id)
            logger.info(
                "tool_cancel_order_executed",
                extra={"customer_id": str(current_user.id), "order_id": str(order_id)},
            )
            return {
                "cancelled": True,
                "order_id": str(cancelled_order.id),
                "status": cancelled_order.status.value,
            }
        except Exception as exc:
            logger.info(
                "tool_cancel_order_failed",
                extra={
                    "customer_id": str(current_user.id),
                    "order_id": str(order_id),
                    "error": str(exc),
                },
            )
            return {"cancelled": False, "error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_cancel_order,
        name="cancel_order",
        description=(
            "Cancel the current customer's own order. This is a HIGH-IMPACT "
            "action -- always call it first with confirmed=false to preview "
            "what would happen, show that to the customer, and only call it "
            "again with confirmed=true after the customer explicitly agrees. "
            "Never set confirmed=true on the first call."
        ),
        args_schema=CancelOrderInput,
    )