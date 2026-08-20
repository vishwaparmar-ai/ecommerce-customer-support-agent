from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from db.dependency import get_db
from db.models import Customer
from schemas.orders import OrderCreate
from services.order_service import (
    create_order,
    cancel_order,
)
from db.dependency import get_current_user


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
)
def create_new_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    order = create_order(
        db=db,
        current_user=current_user,
        data=data,
    )

    return {
        "message": "Order created successfully",
        "order_id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
    }


@router.post(
    "/{order_id}/cancel",
    status_code=status.HTTP_200_OK,
)
def cancel_existing_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    order = cancel_order(
        db=db,
        current_user=current_user,
        order_id=order_id,
    )

    return {
        "message": "Order cancelled successfully",
        "order_id": order.id,
        "status": order.status,
    }