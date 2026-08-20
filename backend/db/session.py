from sqlalchemy.orm import sessionmaker

from db.database import engine

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)