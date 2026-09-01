"""
Refund service.

Encapsulates refund validation and creation so routers stay thin:
    - process_refund: validates the return is complete, the payment was
      actually collected, and no refund already exists, then creates the
      Refund and marks the payment as refunded.

PHASE 7 UPDATE: this is now a staff/admin-executed action (see refund.py
router's require_role gate), not a customer's own action -- the ownership
check comparing ret.customer_id to the caller's id no longer applies,
since the caller is staff acting on a customer's return, not the customer
themselves. `actor` replaces the old `current_user` param name to make
that distinction explicit; logging now records both the staff actor and
the customer who owns the refund, since they're different people.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.logging import logger
from backend.db.models import (
    Customer,
    PaymentStatus,
    Refund,
    RefundStatus,
    Return,
    ReturnStatus,
)


def process_refund(db: Session, actor: Customer, return_id: uuid.UUID) -> Refund:
    """
    Validates, in order, then creates the Refund:
        1. Return exists.
        2. Return is COMPLETED (item received back and accepted).
        3. Order's payment exists and was actually PAID.
        4. No refund already exists for this return.

    `actor` is the staff/admin member executing this refund (authorization
    for that is enforced at the router level via require_role) -- not the
    customer who owns the return. No ownership check against actor.id is
    performed here, since staff legitimately act on any customer's return.

    Creates the Refund in COMPLETED state and marks the Payment as
    REFUNDED. Raises HTTPException on the first rule that fails.

    NOTE: this treats the refund as succeeding immediately once created.
    If you're integrating a real payment gateway's refund API, create the
    Refund in PROCESSING state first, call the gateway, then flip to
    COMPLETED/FAILED based on the gateway's response instead of doing it
    all in one step.
    """
    ret = db.query(Return).filter(Return.id == return_id).first()
    if ret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    if ret.status != ReturnStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Return must be COMPLETED before a refund can be issued (current status: {ret.status.value})",
        )

    order = ret.order
    payment = order.payment if order else None
    if payment is None or payment.status != PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No successful payment found for this order to refund",
        )

    existing_refund = db.query(Refund).filter(Refund.return_id == ret.id).first()
    if existing_refund is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A refund has already been issued for this return",
        )

    try:
        now = datetime.now(timezone.utc)

        refund = Refund(
            id=uuid.uuid4(),
            return_id=ret.id,
            payment_id=payment.id,
            amount=payment.amount,
            status=RefundStatus.COMPLETED,
            refund_reference=f"RFD{uuid.uuid4().hex[:12].upper()}",
            completed_at=now,
        )
        db.add(refund)

        payment.status = PaymentStatus.REFUNDED

        db.commit()
        db.refresh(refund)

        logger.info(
            "refund_processed",
            extra={
                "refund_id": str(refund.id),
                "return_id": str(ret.id),
                "payment_id": str(payment.id),
                "customer_id": str(ret.customer_id),
                "processed_by_staff_id": str(actor.id),
                "amount": str(refund.amount),
            },
        )
        return refund

    except Exception:
        db.rollback()
        logger.exception("refund_processing_failed", extra={"return_id": str(return_id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process refund",
        )