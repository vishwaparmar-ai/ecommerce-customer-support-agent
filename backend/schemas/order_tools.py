from pydantic import BaseModel, Field
from uuid import UUID

class GetOrderInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order to look up")




class ListOrdersInput(BaseModel):
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of recent orders to return (default 10, max 50)",
    )

class TrackShipmentInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order whose shipment should be tracked")



class GetPaymentStatusInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order whose payment status should be checked")


class CheckReturnEligibilityInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order to check return eligibility for")


class GetRefundStatusInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order to check refund status for")

class CreateReturnRequestInput(BaseModel):
    order_id: UUID = Field(description="The UUID of the order to return")
    reason: str = Field(description="Why the customer wants to return this order, in their own words")


