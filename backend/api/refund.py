"""
Refund execution endpoint -- Phase 7 update.

AUTHORIZATION: this now requires SUPPORT_STAFF or ADMIN, closing the gap
flagged when this endpoint was first built ("any customer who owns the
return can trigger their own refund via this endpoint"). Refund execution
is a staff/admin action -- customers can check eligibility via the
check_refund_eligibility agent tool, but actually issuing one requires a
human with staff/admin privileges to review and approve it first.

Note this also changes the semantics slightly: `payload.return_id` is no
longer implicitly the calling customer's own -- process_refund's ownership
check (which compared ret.customer_id to current_user.id) needs revisiting
too, since a staff member reviewing a customer's refund isn't the same
customer. If refund_service.process_refund still checks
ret.customer_id != current_user.id, that check needs to be dropped or
changed now that current_user is staff, not the customer who owns the
return.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, require_role
from backend.db.models import Customer, CustomerRole
from backend.schemas.refunds import OrderRefund
from backend.services.refund_service import process_refund


router = APIRouter(
    prefix="/refund",
    tags=["Refund"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def payment_refund(
    payload: OrderRefund,
    db: Session = Depends(get_db),
    current_staff: Customer = Depends(require_role(CustomerRole.SUPPORT_STAFF, CustomerRole.ADMIN)),
):
    refund = process_refund(
        db=db,
        actor=current_staff,
        return_id=payload.return_id,
    )

    return {
        "message": "Refund processed successfully",
        "refund_id": refund.id,
        "amount": str(refund.amount),
        "status": refund.status.value,
    }