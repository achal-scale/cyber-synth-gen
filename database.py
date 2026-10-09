"""
database.py - Database connection and session management
"""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import os

# Database URL from environment or default to PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://testuser:testpass@localhost:5432/testdb")

# Create engine with connection pooling
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency for FastAPI to get database session.
    Ensures session is closed after request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _has_required_columns(inspector, table_name: str, required: set[str]) -> bool:
    if not inspector.has_table(table_name):
        return True
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    return required.issubset(columns)


def _needs_schema_reset(inspector) -> bool:
    if not inspector.has_table("users"):
        return False

    user_required = {"id", "username", "display_name", "email", "password_hash", "cover_url", "avatar_url"}
    if not _has_required_columns(inspector, "users", user_required):
        return True

    post_required = {"id", "author_id", "content", "created_at", "image_url"}
    if not _has_required_columns(inspector, "posts", post_required):
        return True

    notification_required = {"id", "recipient_id", "actor_id", "type", "created_at", "message_id"}
    if not _has_required_columns(inspector, "notifications", notification_required):
        return True

    return False


def init_db() -> None:
    """
    Initialize database tables.
    Call this on application startup.
    """
    from models import Base

    inspector = inspect(engine)
    if _needs_schema_reset(inspector):
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
