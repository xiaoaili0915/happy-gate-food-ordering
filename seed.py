"""Seed the database with menu data from data/menu_seed.json.

Usage: DATABASE_URL=... python seed.py
(or POST /api/restaurant/admin/seed-menu with the staff token on a deployed server)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, ensure_schema
from app.services.menu_seed import seed_menu


def seed():
    ensure_schema()
    db = SessionLocal()
    try:
        counts = seed_menu(db)
    finally:
        db.close()
    print(f"Menu seeded successfully: {counts}")


if __name__ == "__main__":
    seed()
