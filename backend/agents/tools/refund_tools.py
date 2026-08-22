"""
Agent tools: refunds (read-only).

Wraps refund status lookup as a typed LangChain tool. Takes order_id
rather than refund_id -- a customer naturally knows their order, not an
internal refund ID, and this keeps the input consistent with
get_order/track_shipment/get_payment_status. Internally walks
Order -> Return -> Refund.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session
from backend.db.models import Customer
from backend.services.order_service import get_order_for_customer
from backend.schemas.order_tools import GetRefundStatusInput


def _serialize_refund_status(order) -> dict:
    """
    Walks Order -> Return -> Refund. Your schema enforces at most one
    Return per Order and at most one Refund per Return, so this only
    ever needs to look at the first (only) return, if any.
    """
    if not order.returns:
        return {
            "has_refund": False,
            "message": "No return has been requested for this order, so there is no refund to report.",
        }

    ret = order.returns[0]

    if ret.refund is None:
        return {
            "has_refund": False,
            "return_status": ret.status.value,
            "message": f"No refund has been issued yet, the return is currently '{ret.status.value}'.",
        }

    refund = ret.refund
    return {
        "has_refund": True,
        "return_status": ret.status.value,
        "refund_status": refund.status.value,
        "amount": str(refund.amount),
        "refund_reference": refund.refund_reference,
        "created_at": refund.created_at.isoformat(),
        "completed_at": refund.completed_at.isoformat() if refund.completed_at else None,
    }


def make_get_refund_status_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a get_refund_status tool scoped to current_user. Reuses
    get_order_for_customer for ownership enforcement, same as the other
    order-scoped tools.
    """

    def _get_refund_status(order_id: uuid.UUID) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
            result = _serialize_refund_status(order)
           
            return result
        except Exception as exc:

            return {"error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_get_refund_status,
        name="get_refund_status",
        description=(
            "Check the refund status for the current customer's own order "
            "by its order_id. Returns whether a return/refund exists, the "
            "return's status, and (if a refund was issued) its amount and "
            "status. Only works for orders the customer owns."
        ),
        args_schema=GetRefundStatusInput,
    )