from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from db.dependency import get_db, get_current_user
from db.models import Customer
from schemas.refunds import OrderRefund
from services.refund_service import process_refund


router = APIRouter(
    prefix="/refund",
    tags=["Refund"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def payment_refund(
    payload: OrderRefund,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    refund = process_refund(
        db=db,
        current_user=current_user,
        return_id=payload.return_id,
    )

    return {
        "message": "Refund processed successfully",
        "refund_id": refund.id,
        "amount": str(refund.amount),
        "status": refund.status.value,
    }