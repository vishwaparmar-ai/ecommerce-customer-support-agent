"""
Agent tools: returns.

"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session
from backend.db.models import Customer
from backend.services.return_service import check_return_eligibility
from backend.schemas.order_tools import CheckReturnEligibilityInput
from backend.services.return_service import create_return
from backend.schemas.order_tools import CreateReturnRequestInput


def make_check_return_eligibility_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a check_return_eligibility tool scoped to current_user. This is
    read-only -- it answers "can this order be returned?" without creating
    anything, so the agent can tell a customer whether they're eligible
    before they commit to actually submitting a return (create_return_request,
    a separate write tool).
    """

    def _check_eligibility(order_id: uuid.UUID) -> dict:
        try:
            check_return_eligibility(db, current_user, order_id)
           
            return {"eligible": True}
        except Exception as exc:
            reason = str(getattr(exc, "detail", exc))
           
            return {"eligible": False, "reason": reason}

    return StructuredTool.from_function(
        func=_check_eligibility,
        name="check_return_eligibility",
        description=(
            "Check whether the current customer's own order is eligible "
            "for return, without actually creating a return request. "
            "Returns {eligible: true} or {eligible: false, reason: ...} "
            "explaining why not (not delivered, window expired, "
            "non-returnable category, or a return already exists)."
        ),
        args_schema=CheckReturnEligibilityInput,
    )


"""
write tool - create_return_request
"""

def make_create_return_request_tool(db: Session, current_user: Customer) -> StructuredTool:
    """
    Builds a create_return_request tool scoped to current_user.
    create_return already runs check_return_eligibility internally before
    creating anything, so this tool inherits all of that validation --
    an ineligible order still gets rejected here, it's just now with a
    real write attempted rather than a plain eligibility check.
    """
 
    def _create_return_request(order_id: uuid.UUID, reason: str) -> dict:
        try:
            ret = create_return(db, current_user, order_id, reason)
            
            return {
                "created": True,
                "return_id": str(ret.id),
                "status": ret.status.value,
                "reason": ret.reason,
            }
        except Exception as exc:
            
            return {"created": False, "error": str(getattr(exc, "detail", exc))}
 
    return StructuredTool.from_function(
        func=_create_return_request,
        name="create_return_request",
        description=(
            "Submit a return request for the current customer's own order. "
            "Requires order_id and a reason. This actually creates the "
            "return (in REQUESTED status) if the order is eligible -- it "
            "will fail with the same reasons check_return_eligibility "
            "would report if the order isn't eligible. Only call this "
            "after the customer has confirmed they want to proceed with "
            "the return, not just asked whether they can."
        ),
        args_schema=CreateReturnRequestInput,
    )
 