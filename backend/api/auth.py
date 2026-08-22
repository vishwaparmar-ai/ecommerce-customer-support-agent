from fastapi import APIRouter,HTTPException,status,Depends
from sqlalchemy.orm import Session
from backend.schemas.customer import CustomerCreate,CustomerLogin,CustomerResponse,Token
from backend.db.dependency import get_db
from backend.db.models import Customer
from backend.core.security import hash_password,verify_password,create_access_token


router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=CustomerResponse,status_code=status.HTTP_201_CREATED)
def register(customer:CustomerCreate,db: Session = Depends(get_db)):
    existing_email = db.query(Customer).filter(customer.email == Customer.email).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    existing_username = db.query(Customer).filter(customer.name == Customer.name).first()

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )

    new_user = Customer(
        name=customer.name,
        email=customer.email,
        password_hash=hash_password(customer.password),
        phone=customer.phone
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user



@router.post(
    "/login",
    response_model=Token
)
def login(
    customer: CustomerLogin,
    db: Session = Depends(get_db)
):

    db_user = (
        db.query(Customer)
        .filter(Customer.email == customer.email)
        .first()
    )

    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not verify_password(
        customer.password,
        db_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    access_token = create_access_token(
        {
            "sub": str(db_user.id),
            "email": db_user.email,
            "name": db_user.name
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
