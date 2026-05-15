from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Order, OrderStatus
from app.schemas import OrderApproveIn
from app.services.email import send_order_approved, send_order_rejected
from app.services.printer import print_order

router = APIRouter()


def _verify_token(token: str = Query(...)):
    if token != settings.kitchen_token:
        raise HTTPException(status_code=403, detail="Invalid token")


@router.get("/kitchen")
def kitchen_page(request: Request, token: str = Query(...)):
    _verify_token(token)
    from app.main import templates

    return templates.TemplateResponse(
        "kitchen.html", {"request": request, "token": token}
    )


@router.get("/api/kitchen/orders")
def get_kitchen_orders(token: str = Query(...), db: Session = Depends(get_db)):
    _verify_token(token)
    orders = (
        db.query(Order)
        .filter(Order.status == OrderStatus.pending_restaurant_confirmation)
        .order_by(Order.created_at.asc())
        .all()
    )
    result = []
    for o in orders:
        items = []
        for item in o.items:
            items.append({
                "name": item.item_name,
                "quantity": item.quantity,
                "unit_price_cents": item.unit_price_cents,
                "special_notes": item.special_notes,
                "modifiers": [{"name": m.modifier_name, "price_cents": m.price_cents} for m in item.modifiers],
            })
        result.append({
            "id": o.id,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "pickup_notes": o.pickup_notes,
            "subtotal_cents": o.subtotal_cents,
            "created_at": o.created_at.isoformat(),
            "expires_at": o.expires_at.isoformat(),
            "items": items,
        })
    return result


@router.post("/api/orders/{order_id}/approve")
def approve_order(
    order_id: int,
    payload: OrderApproveIn,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    _verify_token(token)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.pending_restaurant_confirmation:
        raise HTTPException(status_code=400, detail="Order cannot be approved")

    order.status = OrderStatus.approved
    order.approved_at = datetime.now(timezone.utc)
    order.expected_pickup_time = payload.expected_pickup_time
    db.commit()
    db.refresh(order)

    try:
        send_order_approved(order)
    except Exception:
        pass

    try:
        print_order(order)
    except Exception:
        pass

    return {"status": "approved", "expected_pickup_time": order.expected_pickup_time}


@router.post("/api/orders/{order_id}/reject")
def reject_order(
    order_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    _verify_token(token)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.pending_restaurant_confirmation:
        raise HTTPException(status_code=400, detail="Order cannot be rejected")

    order.status = OrderStatus.rejected_manual
    order.rejected_at = datetime.now(timezone.utc)
    db.commit()

    try:
        send_order_rejected(order)
    except Exception:
        pass

    return {"status": "rejected"}
