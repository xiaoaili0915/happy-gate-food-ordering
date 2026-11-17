"""An orders.db created before the restaurant app gains the new columns on startup."""
import sqlite3

from sqlalchemy import create_engine, inspect


def test_ensure_schema_adds_missing_columns(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, status VARCHAR(30), customer_name VARCHAR(200),"
        " customer_email VARCHAR(200), customer_phone VARCHAR(50), pickup_notes TEXT, subtotal_cents INTEGER,"
        " created_at DATETIME, expires_at DATETIME, approved_at DATETIME, rejected_at DATETIME,"
        " expected_pickup_time VARCHAR(50))"
    )
    con.commit()
    con.close()

    import app.database as database

    old_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", old_engine)
    database.ensure_schema()

    cols = {c["name"] for c in inspect(old_engine).get_columns("orders")}
    assert {"preparation_minutes", "estimated_ready_at", "ready_at", "completed_at", "rejection_reason"} <= cols
    assert "print_events" in inspect(old_engine).get_table_names()
    assert "device_tokens" in inspect(old_engine).get_table_names()
