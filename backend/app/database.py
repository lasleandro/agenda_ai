"""
Database configuration — single source of truth for the SQLAlchemy engine,
session factory, and declarative base.

Connection resolution order:

1. ``DATABASE_URL`` — a complete SQLAlchemy URL. Used verbatim in deployed
   environments (e.g. Cloud SQL private IP, or a unix socket via
   ``?host=/cloudsql/PROJECT:REGION:INSTANCE``).
2. ``PG_LOCAL_*`` — discrete parts, for local development.

Pool sizing is read from the environment so every deployed process (API,
workers, webhook processor, migrations) can be tuned against the database
tier without a code change. Defaults match the historical local values.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Load .env from the project root (two levels up from this file). Deployed
# environments inject real environment variables and simply have no .env.
# ---------------------------------------------------------------------------
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, ".env"))


def _local_pg_url() -> str:
    """Build a PostgreSQL DSN from discrete PG_LOCAL_* variables."""
    user = os.getenv("PG_LOCAL_USER", "cityfoundry")
    password = os.getenv("PG_LOCAL_PASSWORD", "cityfoundry_dev")
    host = os.getenv("PG_LOCAL_HOST", "localhost")
    port = os.getenv("PG_LOCAL_PORT", "5433")
    db = os.getenv("AGENDA_LOCAL_DATABASE", "agenda_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _resolve_database_url() -> str:
    """Prefer an explicit DATABASE_URL; fall back to local parts."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return _local_pg_url()
    # Managed providers often hand out the legacy ``postgres://`` scheme,
    # which SQLAlchemy 2.x no longer recognises.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


DATABASE_URL: str = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_size=_int_env("DB_POOL_SIZE", 5),
    max_overflow=_int_env("DB_MAX_OVERFLOW", 10),
    pool_timeout=_int_env("DB_POOL_TIMEOUT", 30),
    pool_recycle=_int_env("DB_POOL_RECYCLE", 1800),
    # Cheap SELECT 1 before handing out a pooled connection — avoids
    # "server closed the connection unexpectedly" after a Cloud SQL
    # failover or an idle-timeout drop.
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
