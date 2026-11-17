import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)


def _send_email(to: str, subject: str, html: str):
    if not settings.resend_api_key:
        logger.warning(f"Email not sent (no API key): {subject} -> {to}")
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {"from": settings.from_email, "to": to, "subject": subject, "html": html}
    )


def send_order_approved(order):
    html = f"""
    <h2>Your order has been confirmed!</h2>
    <p>Hi {order.customer_name},</p>
    <p>Your order #{order.id} has been approved.</p>
    <p><strong>Expected pickup time: {order.expected_pickup_time}</strong></p>
    <p>See you soon!</p>
    """
    _send_email(order.customer_email, "Order Confirmed - Pickup Details", html)


def send_order_rejected(order):
    reason = "timed out" if order.status.value == "rejected_timeout" else "declined"
    html = f"""
    <h2>Order Update</h2>
    <p>Hi {order.customer_name},</p>
    <p>Unfortunately, your order #{order.id} was {reason}.</p>
    <p>Please try again or contact the restaurant directly.</p>
    """
    _send_email(order.customer_email, "Order Update", html)
