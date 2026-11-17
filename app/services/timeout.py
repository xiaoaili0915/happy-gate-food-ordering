import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Order, OrderStatus

logger = logging.getLogger(__name__)


def expire_pending(db) -> int:
    """Reject pending orders past their expiry. Safe to call on every read.

    Called from the order endpoints (website status page, kitchen page, app
    polling), so the 3-minute timeout works without a background process.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # columns are naive UTC
    stmt = select(Order).where(
        Order.status == OrderStatus.pending_restaurant_confirmation,
        Order.expires_at <= now,
    )
    expired_orders = db.execute(stmt).scalars().all()
    for order in expired_orders:
        order.status = OrderStatus.rejected_timeout
        order.rejected_at = now
        logger.info(f"Order {order.id} auto-rejected (timeout)")
    if expired_orders:
        db.commit()
    return len(expired_orders)
