from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from backend.core.config import settings
from fastapi import HTTPException,status
from jose import JWTError, jwt

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)




def verify_jwt_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    Returns the token payload if valid.
    Raises HTTP 401 if invalid or expired.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

    except JWTError:
        raise credentials_exception

    # -----------------------------------------
    # Validate required claims
    # -----------------------------------------

    customer_id = payload.get("sub")

    if customer_id is None:
        raise credentials_exception

    return payload