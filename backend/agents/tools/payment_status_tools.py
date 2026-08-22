"""
Agent tools: payments.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session
from backend.db.models import Customer
from backend.services.order_service import get_order_for_customer
from backend.schemas.order_tools import GetPaymentStatusInput


def _serialize_payment(order) -> dict:
    """
    Converts an Order's payment into a plain, JSON-safe dict for the LLM.
    Every Order should have exactly one Payment (unique FK per your schema),
    but this still guards against a missing row defensively.
    """
    if order.payment is None:
        return {
            "has_payment": False,
            "message": "No payment record found for this order.",
        }

    payment = order.payment
    return {
        "has_payment": True,
        "amount": str(payment.amount),
        "method": payment.method.value,
        "status": payment.status.value,
        "transaction_reference": payment.transaction_reference,
        "created_at": payment.created_at.isoformat(),
    }


def make_get_payment_status_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a get_payment_status tool scoped to current_user. Reuses
    get_order_for_customer for the same ownership enforcement as the other
    order-scoped tools -- a customer can only check payment status for
    orders they actually own.
    """

    def _get_payment_status(order_id: uuid.UUID) -> dict:
        try:
            order = get_order_for_customer(db, order_id, current_user.id)
            result = _serialize_payment(order)
            return result
        except Exception as exc:
        
            return {"error": str(getattr(exc, "detail", exc))}

    return StructuredTool.from_function(
        func=_get_payment_status,
        name="get_payment_status",
        description=(
            "Check the payment status of the current customer's own order "
            "by its order_id. Returns amount, payment method, status (e.g. "
            "paid, failed, refunded), and transaction reference. Only works "
            "for orders the customer owns."
        ),
        args_schema=GetPaymentStatusInput,
    )