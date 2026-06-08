"""
SQLAlchemy 2.x database setup.

Uses SQLite stored at backend/portfolio.db by default (configurable via
DATABASE_URL).  For a local single-user tool this is perfectly adequate.

Usage:
    from app.database import get_db, init_db

    # In FastAPI endpoints, inject the session:
    def endpoint(db: Session = Depends(get_db)):
        ...

    # On application startup:
    init_db()
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not already exist.

    Called once on application startup.  Safe to call multiple times.
    """
    # Import all models so their tables are registered on Base.metadata
    import app.models.account       # noqa: F401
    import app.models.transaction   # noqa: F401
    import app.models.ledger        # noqa: F401
    import app.models.holding       # noqa: F401
    import app.models.watchlist     # noqa: F401
    import app.models.cash          # noqa: F401

    Base.metadata.create_all(bind=engine)
