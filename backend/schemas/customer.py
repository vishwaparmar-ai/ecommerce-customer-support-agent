from pydantic import BaseModel, EmailStr
from uuid import UUID
from backend.db.models import CustomerRole

class CustomerCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: str | None = None

class CustomerLogin(BaseModel):
    email: EmailStr
    password: str

class CustomerResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: CustomerRole = CustomerRole.CUSTOMER
    phone: str | None = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str

class QueryRequest(BaseModel):
    dataset_id:int
    question:str