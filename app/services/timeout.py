import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Order, OrderStatus

logger = logging.getLogger(__name__)


async def check_expired_orders():
    """Find pending orders past their expiry and reject them."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
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
    finally:
        db.close()


async def timeout_loop():
    """Background loop that checks for expired orders every 30 seconds."""
    while True:
        try:
            await check_expired_orders()
        except Exception as e:
            logger.error(f"Timeout checker error: {e}")
        await asyncio.sleep(30)
