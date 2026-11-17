import os
import pathlib

# Must be set before the app (and its Settings) is imported.
_db = pathlib.Path(__file__).parent / "test_orders.db"
if _db.exists():
    _db.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["KITCHEN_TOKEN"] = "test-token"
os.environ["FIREBASE_CREDENTIALS"] = ""
os.environ["RESEND_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def new_order(client):
    """Create a customer order and return its id."""
    def _create(name="Test Customer"):
        payload = {
            "customer_name": name,
            "customer_email": "test@example.com",
            "customer_phone": "0612345678",
            "pickup_notes": "ring the bell",
            "items": [
                {
                    "menu_item_id": 1,
                    "item_name": "Babi Pangang",
                    "quantity": 2,
                    "unit_price_cents": 1250,
                    "special_notes": "extra spicy",
                    "modifiers": [{"modifier_name": "Nasi", "price_cents": 0}],
                }
            ],
        }
        r = client.post("/api/orders", json=payload)
        assert r.status_code == 200, r.text
        return r.json()["order_id"]
    return _create
