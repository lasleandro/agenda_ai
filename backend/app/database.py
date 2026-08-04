"""
Database configuration — single source of truth for the SQLAlchemy engine,
session factory, and declarative base.

Reads connection parameters from .env via the project root.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Load .env from the project root (two levels up from this file)
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, ".env"))


def _pg_url() -> str:
    """Build a PostgreSQL DSN from .env variables."""
    user = os.getenv("PG_LOCAL_USER", "cityfoundry")
    password = os.getenv("PG_LOCAL_PASSWORD", "cityfoundry_dev")
    host = os.getenv("PG_LOCAL_HOST", "localhost")
    port = os.getenv("PG_LOCAL_PORT", "5433")
    db = os.getenv("AGENDA_LOCAL_DATABASE", "agenda_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL: str = _pg_url()

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
