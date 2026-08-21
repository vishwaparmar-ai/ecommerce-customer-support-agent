from pydantic import BaseModel
from uuid import UUID

class ReturnRequest(BaseModel):
    order_id:UUID
    reason:str