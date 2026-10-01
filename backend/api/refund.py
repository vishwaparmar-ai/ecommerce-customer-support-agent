from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user, require_role
from backend.db.models import Customer, CustomerRole
from backend.schemas.refunds import OrderRefund, RefundResponse
from backend.services.refund_service import get_refund_for_customer, process_refund

router = APIRouter(
    prefix="/refunds",
    tags=["Refunds"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def payment_refund(
    payload: OrderRefund,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    """Staff/Admin only: Process a refund for an approved completed return."""
    refund = process_refund(
        db=db,
        actor=current_staff,
        return_id=payload.return_id,
    )

    return {
        "message": "Refund processed successfully",
        "refund_id": str(refund.id),
        "amount": str(refund.amount),
        "status": refund.status.value,
    }


@router.get("/{refund_id}", response_model=RefundResponse)
def get_refund_status(
    refund_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Inspect refund status and details for an owned return or as staff/admin."""
    refund = get_refund_for_customer(db=db, refund_id=refund_id, current_user=current_user)
    return RefundResponse(
        id=refund.id,
        return_id=refund.return_id,
        payment_id=refund.payment_id,
        amount=refund.amount,
        status=refund.status,
        refund_reference=refund.refund_reference,
        created_at=refund.created_at,
        completed_at=refund.completed_at,
    )