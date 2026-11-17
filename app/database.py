from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

def _engine_url(url: str) -> str:
    """Neon/Vercel hand out postgres:// or postgresql:// URLs; route them to psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_url = _engine_url(settings.database_url)
if _url.startswith("sqlite"):
    engine = create_engine(_url, connect_args={"check_same_thread": False})
else:
    # Timestamps are stored naive-UTC; pin the session timezone so Postgres
    # never shifts them. pool_pre_ping survives Neon's idle auto-suspend.
    engine = create_engine(
        _url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Create tables and add columns introduced after the initial release.

    SQLAlchemy's create_all never alters existing tables, so an orders.db
    created before the restaurant app would lack the new columns.
    """
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("orders")}
    wanted = {
        "preparation_minutes": "INTEGER",
        "estimated_ready_at": "TIMESTAMP",
        "ready_at": "TIMESTAMP",
        "completed_at": "TIMESTAMP",
        "rejection_reason": "TEXT DEFAULT ''",
    }
    with engine.begin() as conn:
        for name, ddl in wanted.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))
