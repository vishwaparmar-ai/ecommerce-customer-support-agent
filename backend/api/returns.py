from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.db.dependency import get_db, get_current_user
from backend.db.models import Customer
from backend.schemas.return_order import ReturnRequest, ReturnResponse
from backend.services.return_service import (
    create_return,
    get_return_for_customer,
    list_returns_for_customer,
)

router = APIRouter(
    prefix="/returns",
    tags=["Returns"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_new_return_request(
    payload: ReturnRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Submit a return request for an eligible delivered order."""
    return_request = create_return(
        order_id=payload.order_id,
        reason=payload.reason,
        db=db,
        current_user=current_user,
    )

    return {
        "message": "Return request accepted successfully",
        "return_id": str(return_request.id),
        "status": return_request.status.value,
    }


@router.get("/", response_model=list[ReturnResponse])
def list_my_returns(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """List all return requests for the authenticated customer."""
    returns = list_returns_for_customer(db=db, customer_id=current_user.id)
    return [
        ReturnResponse(
            id=r.id,
            order_id=r.order_id,
            customer_id=r.customer_id,
            reason=r.reason,
            status=r.status,
            requested_at=r.requested_at,
            approved_at=r.approved_at,
            completed_at=r.completed_at,
        )
        for r in returns
    ]


@router.get("/{return_id}", response_model=ReturnResponse)
def get_return_details(
    return_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Get details of a return request owned by the authenticated customer."""
    r = get_return_for_customer(db=db, return_id=return_id, customer_id=current_user.id)
    return ReturnResponse(
        id=r.id,
        order_id=r.order_id,
        customer_id=r.customer_id,
        reason=r.reason,
        status=r.status,
        requested_at=r.requested_at,
        approved_at=r.approved_at,
        completed_at=r.completed_at,
    )
