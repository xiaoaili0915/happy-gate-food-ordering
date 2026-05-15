from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderItem, OrderItemModifier, OrderStatus
from app.schemas import OrderCreateIn
from app.services.email import send_new_order_to_restaurant

router = APIRouter()


@router.post("/api/orders")
def create_order(payload: OrderCreateIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    subtotal = 0
    for item in payload.items:
        item_total = item.unit_price_cents * item.quantity
        item_total += sum(m.price_cents for m in item.modifiers) * item.quantity
        subtotal += item_total

    order = Order(
        status=OrderStatus.pending_restaurant_confirmation,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        pickup_notes=payload.pickup_notes,
        subtotal_cents=subtotal,
        created_at=now,
        expires_at=now + timedelta(minutes=3),
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        oi = OrderItem(
            order_id=order.id,
            menu_item_id=item.menu_item_id,
            item_name=item.item_name,
            quantity=item.quantity,
            unit_price_cents=item.unit_price_cents,
            special_notes=item.special_notes,
        )
        db.add(oi)
        db.flush()

        for mod in item.modifiers:
            oim = OrderItemModifier(
                order_item_id=oi.id,
                modifier_name=mod.modifier_name,
                price_cents=mod.price_cents,
            )
            db.add(oim)

    db.commit()
    db.refresh(order)

    try:
        send_new_order_to_restaurant(order)
    except Exception:
        pass

    return {"order_id": order.id, "status": order.status.value}


@router.get("/order/{order_id}")
def order_status_page(order_id: int, request: Request, db: Session = Depends(get_db)):
    from app.main import templates

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return templates.TemplateResponse(
            "order_status.html", {"request": request, "order": None}
        )
    return templates.TemplateResponse(
        "order_status.html", {"request": request, "order": order}
    )


@router.get("/api/orders/{order_id}")
def get_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return {"error": "not found"}, 404
    return {
        "id": order.id,
        "status": order.status.value,
        "expected_pickup_time": order.expected_pickup_time,
        "created_at": order.created_at.isoformat(),
    }
