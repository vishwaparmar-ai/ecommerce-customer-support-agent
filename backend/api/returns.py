from uuid import UUID

from fastapi import APIRouter, Depends, status,HTTPException
from sqlalchemy.orm import Session

from db.dependency import get_db
from db.models import Customer
from schemas.return_order import ReturnRequest
from services.return_service import (
   create_return,
   check_return_eligibility
)
from db.dependency import get_current_user


router = APIRouter(
    prefix="/product_return",
    tags=["Return"],
)


@router.post("/",status_code=status.HTTP_202_ACCEPTED)
def create_new_return_request(
    payload:ReturnRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):


        
    return_request = create_return(
        order_id=payload.order_id,
        reason=payload.reason,
        db=db,
        current_user=current_user
    )

    return {
            "message": "Return request accepted successfully",
            "request_id": return_request.id
        }


