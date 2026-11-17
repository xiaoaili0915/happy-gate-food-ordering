from datetime import datetime, timedelta, timezone


def test_requires_bearer_token(client):
    assert client.get("/api/restaurant/orders").status_code == 401
    assert client.get("/api/restaurant/orders", headers={"Authorization": "Bearer nope"}).status_code == 401
    # legacy query-token style is not accepted on the new API
    assert client.get("/api/restaurant/orders?token=test-token").status_code == 401


def test_ping(client, auth):
    r = client.get("/api/restaurant/ping", headers=auth)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["restaurant_name"]


def test_new_order_appears_in_pending_with_details(client, auth, new_order):
    oid = new_order("Pending Person")
    r = client.get("/api/restaurant/orders?scope=pending", headers=auth)
    assert r.status_code == 200
    order = next(o for o in r.json() if o["id"] == oid)
    assert order["status"] == "pending_restaurant_confirmation"
    assert order["customer_name"] == "Pending Person"
    assert order["subtotal_cents"] == 2500
    assert order["items"][0]["name"] == "Babi Pangang"
    assert order["items"][0]["modifiers"][0]["name"] == "Nasi"
    assert order["items"][0]["special_notes"] == "extra spicy"
    assert order["created_at"].endswith("+00:00")
    assert order["print_events"] == []


def test_accept_sets_server_computed_ready_time(client, auth, new_order):
    oid = new_order()
    before = datetime.now(timezone.utc)
    r = client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 30}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["preparation_minutes"] == 30
    ready = datetime.fromisoformat(body["estimated_ready_at"])
    assert timedelta(minutes=29) < ready - before < timedelta(minutes=31)
    # website-compatible local HH:MM is derived from the same instant
    assert len(body["expected_pickup_time"]) == 5 and body["expected_pickup_time"][2] == ":"

    # customer status endpoint reflects it
    s = client.get(f"/api/orders/{oid}").json()
    assert s["status"] == "approved"
    assert s["expected_pickup_time"] == body["expected_pickup_time"]
    assert s["estimated_ready_at"]

    # moves from pending to active
    pending_ids = [o["id"] for o in client.get("/api/restaurant/orders?scope=pending", headers=auth).json()]
    active_ids = [o["id"] for o in client.get("/api/restaurant/orders?scope=active", headers=auth).json()]
    assert oid not in pending_ids and oid in active_ids


def test_accept_is_idempotent_and_rejects_bad_minutes(client, auth, new_order):
    oid = new_order()
    assert client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 0}, headers=auth).status_code == 422
    first = client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 15}, headers=auth).json()
    second = client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 45}, headers=auth)
    assert second.status_code == 200
    # duplicate tap does not change the already-confirmed time
    assert second.json()["estimated_ready_at"] == first["estimated_ready_at"]
    assert second.json()["preparation_minutes"] == 15


def test_reject_with_reason_then_conflicts(client, auth, new_order):
    oid = new_order()
    r = client.post(f"/api/restaurant/orders/{oid}/reject", json={"reason": "Out of duck"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected_manual"
    assert r.json()["rejection_reason"] == "Out of duck"
    # idempotent repeat
    assert client.post(f"/api/restaurant/orders/{oid}/reject", json={"reason": "again"}, headers=auth).status_code == 200
    # cannot accept a rejected order
    assert client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 15}, headers=auth).status_code == 409
    # shows up in history, searchable by number
    hist = client.get(f"/api/restaurant/orders?scope=history&q=%23{oid}", headers=auth).json()
    assert [o["id"] for o in hist] == [oid]


def test_full_lifecycle_pending_accept_ready_complete(client, auth, new_order):
    oid = new_order()
    assert client.post(f"/api/restaurant/orders/{oid}/ready", headers=auth).status_code == 409  # not accepted yet
    client.post(f"/api/restaurant/orders/{oid}/accept", json={"preparation_minutes": 15}, headers=auth)

    r = client.post(f"/api/restaurant/orders/{oid}/ready", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "ready" and r.json()["ready_at"]
    assert client.get(f"/api/orders/{oid}").json()["status"] == "ready"
    assert client.post(f"/api/restaurant/orders/{oid}/ready", headers=auth).status_code == 200  # idempotent
    # ready orders stay in the active list until picked up
    assert oid in [o["id"] for o in client.get("/api/restaurant/orders?scope=active", headers=auth).json()]

    r = client.post(f"/api/restaurant/orders/{oid}/complete", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert oid not in [o["id"] for o in client.get("/api/restaurant/orders?scope=active", headers=auth).json()]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert oid in [o["id"] for o in client.get(f"/api/restaurant/orders?scope=history&date={today}", headers=auth).json()]
    assert client.get("/api/restaurant/orders?scope=history&date=bad", headers=auth).status_code == 400


def test_print_events_are_recorded_and_returned(client, auth, new_order):
    oid = new_order()
    assert client.post(f"/api/restaurant/orders/{oid}/print-events", json={"status": "bogus"}, headers=auth).status_code == 422
    for st, msg in [("queued", ""), ("sending", ""), ("failed", "Connection refused"), ("printed", "")]:
        r = client.post(f"/api/restaurant/orders/{oid}/print-events",
                        json={"status": st, "message": msg, "device": "Pixel 7"}, headers=auth)
        assert r.status_code == 200
    events = client.get(f"/api/restaurant/orders/{oid}", headers=auth).json()["print_events"]
    assert [e["status"] for e in events] == ["queued", "sending", "failed", "printed"]
    assert events[2]["message"] == "Connection refused"
    assert events[0]["device"] == "Pixel 7"


def test_device_registration_upserts(client, auth):
    assert client.post("/api/restaurant/devices/register", json={"token": ""}, headers=auth).status_code == 422
    assert client.post("/api/restaurant/devices/register", json={"token": "abc"}, headers=auth).status_code == 200
    assert client.post("/api/restaurant/devices/register", json={"token": "abc"}, headers=auth).status_code == 200
    from app.database import SessionLocal
    from app.models import DeviceToken
    db = SessionLocal()
    try:
        assert db.query(DeviceToken).filter(DeviceToken.token == "abc").count() == 1
    finally:
        db.close()


def test_legacy_web_kitchen_approve_still_works_and_fills_ready_time(client, auth, new_order):
    oid = new_order()
    r = client.post(f"/api/orders/{oid}/approve?token=test-token", json={"expected_pickup_time": "18:30"})
    assert r.status_code == 200
    order = client.get(f"/api/restaurant/orders/{oid}", headers=auth).json()
    assert order["status"] == "approved"
    assert order["expected_pickup_time"] == "18:30"
    assert order["estimated_ready_at"] is not None


def test_404_for_unknown_order(client, auth):
    assert client.get("/api/restaurant/orders/999999", headers=auth).status_code == 404
    assert client.post("/api/restaurant/orders/999999/accept", json={"preparation_minutes": 15}, headers=auth).status_code == 404
