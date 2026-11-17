"""Authenticated API for the restaurant Android order-taking app.

Auth: ``Authorization: Bearer <KITCHEN_TOKEN>``. State transitions are
enforced server-side and accept/reject/ready/complete are idempotent: repeating
a call that already succeeded returns 200 with the current order instead of
changing anything, so duplicate taps or retries cannot double-apply.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import DeviceToken, Order, OrderStatus, PrintEvent
from app.schemas import AcceptIn, DeviceRegisterIn, PrintEventIn, RejectIn
from app.services.email import send_order_approved, send_order_rejected
from app.services.menu_seed import seed_menu
from app.services.timeout import expire_pending

router = APIRouter(prefix="/api/restaurant")

PRINT_STATUSES = {"queued", "sending", "printed", "failed", "uncertain"}
ACTIVE_STATUSES = (OrderStatus.approved, OrderStatus.ready)
HISTORY_STATUSES = (
    OrderStatus.completed,
    OrderStatus.rejected_manual,
    OrderStatus.rejected_timeout,
)


def require_staff(authorization: str = Header(default="")):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.kitchen_token:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


def _utc(dt: datetime | None) -> datetime | None:
    """Timestamps are stored naive in UTC; make them explicit."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    dt = _utc(dt)
    return dt.isoformat() if dt else None


def _local_hhmm(dt: datetime) -> str:
    return _utc(dt).astimezone(ZoneInfo(settings.restaurant_timezone)).strftime("%H:%M")


def order_to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "status": o.status.value,
        "customer_name": o.customer_name,
        "customer_email": o.customer_email,
        "customer_phone": o.customer_phone,
        "pickup_notes": o.pickup_notes,
        "subtotal_cents": o.subtotal_cents,
        "created_at": _iso(o.created_at),
        "expires_at": _iso(o.expires_at),
        "approved_at": _iso(o.approved_at),
        "rejected_at": _iso(o.rejected_at),
        "ready_at": _iso(o.ready_at),
        "completed_at": _iso(o.completed_at),
        "preparation_minutes": o.preparation_minutes,
        "estimated_ready_at": _iso(o.estimated_ready_at),
        "expected_pickup_time": o.expected_pickup_time,
        "rejection_reason": o.rejection_reason or "",
        "items": [
            {
                "name": i.item_name,
                "quantity": i.quantity,
                "unit_price_cents": i.unit_price_cents,
                "special_notes": i.special_notes,
                "modifiers": [
                    {"name": m.modifier_name, "price_cents": m.price_cents} for m in i.modifiers
                ],
            }
            for i in o.items
        ],
        "print_events": [
            {
                "status": e.status,
                "message": e.message,
                "device": e.device,
                "created_at": _iso(e.created_at),
            }
            for e in o.print_events
        ],
    }


def _get_order(db: Session, order_id: int) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/ping", dependencies=[Depends(require_staff)])
def ping():
    return {
        "ok": True,
        "restaurant_name": settings.restaurant_name,
        "timezone": settings.restaurant_timezone,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/orders", dependencies=[Depends(require_staff)])
def list_orders(
    scope: str = Query("pending", pattern="^(pending|active|history)$"),
    date: str | None = Query(None, description="YYYY-MM-DD, restaurant-local, history only"),
    q: str | None = Query(None, description="Order number, history only"),
    db: Session = Depends(get_db),
):
    expire_pending(db)
    query = db.query(Order)
    if scope == "pending":
        query = query.filter(Order.status == OrderStatus.pending_restaurant_confirmation)
        query = query.order_by(Order.created_at.asc())
    elif scope == "active":
        query = query.filter(Order.status.in_(ACTIVE_STATUSES))
        query = query.order_by(Order.estimated_ready_at.asc(), Order.created_at.asc())
    else:
        query = query.filter(Order.status.in_(HISTORY_STATUSES))
        if q:
            try:
                query = query.filter(Order.id == int(q.lstrip("#")))
            except ValueError:
                raise HTTPException(status_code=400, detail="q must be an order number")
        if date:
            try:
                day = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
            tz = ZoneInfo(settings.restaurant_timezone)
            start = day.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
            query = query.filter(Order.created_at >= start, Order.created_at < start + timedelta(days=1))
        query = query.order_by(Order.created_at.desc()).limit(200)
    return [order_to_dict(o) for o in query.all()]


@router.get("/orders/{order_id}", dependencies=[Depends(require_staff)])
def get_order(order_id: int, db: Session = Depends(get_db)):
    expire_pending(db)
    return order_to_dict(_get_order(db, order_id))


@router.post("/orders/{order_id}/accept", dependencies=[Depends(require_staff)])
def accept_order(order_id: int, payload: AcceptIn, db: Session = Depends(get_db)):
    if not 1 <= payload.preparation_minutes <= 240:
        raise HTTPException(status_code=422, detail="preparation_minutes must be 1-240")
    expire_pending(db)
    order = _get_order(db, order_id)
    if order.status == OrderStatus.approved:
        return order_to_dict(order)  # idempotent
    if order.status != OrderStatus.pending_restaurant_confirmation:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    now = datetime.now(timezone.utc)
    order.status = OrderStatus.approved
    order.approved_at = now
    order.preparation_minutes = payload.preparation_minutes
    order.estimated_ready_at = now + timedelta(minutes=payload.preparation_minutes)
    order.expected_pickup_time = _local_hhmm(order.estimated_ready_at)
    db.commit()
    db.refresh(order)

    try:
        send_order_approved(order)
    except Exception:
        pass
    return order_to_dict(order)


@router.post("/orders/{order_id}/reject", dependencies=[Depends(require_staff)])
def reject_order(order_id: int, payload: RejectIn, db: Session = Depends(get_db)):
    expire_pending(db)
    order = _get_order(db, order_id)
    if order.status == OrderStatus.rejected_manual:
        return order_to_dict(order)  # idempotent
    if order.status != OrderStatus.pending_restaurant_confirmation:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    order.status = OrderStatus.rejected_manual
    order.rejected_at = datetime.now(timezone.utc)
    order.rejection_reason = payload.reason.strip()
    db.commit()
    db.refresh(order)

    try:
        send_order_rejected(order)
    except Exception:
        pass
    return order_to_dict(order)


@router.post("/orders/{order_id}/ready", dependencies=[Depends(require_staff)])
def mark_ready(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status == OrderStatus.ready:
        return order_to_dict(order)  # idempotent
    if order.status != OrderStatus.approved:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    order.status = OrderStatus.ready
    order.ready_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return order_to_dict(order)


@router.post("/orders/{order_id}/complete", dependencies=[Depends(require_staff)])
def mark_completed(order_id: int, db: Session = Depends(get_db)):
    order = _get_order(db, order_id)
    if order.status == OrderStatus.completed:
        return order_to_dict(order)  # idempotent
    if order.status != OrderStatus.ready:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    order.status = OrderStatus.completed
    order.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return order_to_dict(order)


@router.post("/orders/{order_id}/print-events", dependencies=[Depends(require_staff)])
def record_print_event(order_id: int, payload: PrintEventIn, db: Session = Depends(get_db)):
    if payload.status not in PRINT_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(PRINT_STATUSES)}")
    order = _get_order(db, order_id)
    db.add(
        PrintEvent(
            order_id=order.id,
            status=payload.status,
            message=payload.message[:1000],
            device=payload.device[:100],
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(order)
    return order_to_dict(order)


@router.post("/devices/register", dependencies=[Depends(require_staff)])
def register_device(payload: DeviceRegisterIn, db: Session = Depends(get_db)):
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=422, detail="token required")
    device = db.query(DeviceToken).filter(DeviceToken.token == token).first()
    now = datetime.now(timezone.utc)
    if device:
        device.updated_at = now
        device.platform = payload.platform
    else:
        db.add(DeviceToken(token=token, platform=payload.platform, created_at=now, updated_at=now))
    db.commit()
    return {"ok": True}


@router.post("/admin/seed-menu", dependencies=[Depends(require_staff)])
def admin_seed_menu(db: Session = Depends(get_db)):
    """(Re)load the menu from data/menu_seed.json. Run once after deploying to a fresh database."""
    counts = seed_menu(db)
    return {"ok": True, **counts}
