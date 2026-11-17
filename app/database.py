from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
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
        "estimated_ready_at": "DATETIME",
        "ready_at": "DATETIME",
        "completed_at": "DATETIME",
        "rejection_reason": "TEXT DEFAULT ''",
    }
    with engine.begin() as conn:
        for name, ddl in wanted.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))
