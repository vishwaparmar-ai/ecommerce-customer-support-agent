from backend.db.session import SessionLocal
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.db.models import CustomerRole
from backend.db.models import Customer
from backend.core.security import verify_jwt_token
from uuid import UUID

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()





def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    payload = verify_jwt_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user = db.query(Customer).filter(
        Customer.id == UUID(payload["sub"])
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user

def require_role(*allowed_roles: CustomerRole):
    """
    Returns a FastAPI dependency that only allows customers whose role is
    in allowed_roles. Raises 403 for anyone else -- including a perfectly
    valid, authenticated customer whose role just isn't sufficient.
    """
 
    def _require_role(current_user: Customer = Depends(get_current_user)) -> Customer:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user
 
    return _require_role
 