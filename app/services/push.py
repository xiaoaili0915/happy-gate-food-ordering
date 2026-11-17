"""Firebase Cloud Messaging (HTTP v1) push to registered restaurant devices.

Push is best-effort: orders are persisted before we notify, and the app
reconciles by fetching outstanding orders on launch/resume and by polling
while in the foreground. If FIREBASE_CREDENTIALS is empty this is a no-op.
"""
import json
import logging
import os

from app.config import settings
from app.database import SessionLocal
from app.models import DeviceToken

logger = logging.getLogger(__name__)

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _load_credentials():
    raw = settings.firebase_credentials.strip()
    if not raw:
        return None
    from google.oauth2 import service_account

    if raw.startswith("{"):
        info = json.loads(raw)
    elif os.path.exists(raw):
        with open(raw) as f:
            info = json.load(f)
    else:
        logger.error("FIREBASE_CREDENTIALS is neither JSON nor an existing file")
        return None
    return service_account.Credentials.from_service_account_info(info, scopes=[_FCM_SCOPE])


def notify_new_order(order_id: int, customer_name: str, total_cents: int) -> int:
    """Send a high-priority data+notification message to every registered device.

    Returns the number of successful sends. Never raises.
    """
    try:
        creds = _load_credentials()
    except Exception as e:  # malformed credentials
        logger.error(f"FCM credentials error: {e}")
        return 0
    if creds is None:
        logger.info(f"Push disabled, not notifying order #{order_id}")
        return 0

    import httpx
    from google.auth.transport.requests import Request

    db = SessionLocal()
    try:
        tokens = db.query(DeviceToken).all()
        if not tokens:
            return 0
        creds.refresh(Request())
        url = f"https://fcm.googleapis.com/v1/projects/{creds.project_id}/messages:send"
        headers = {"Authorization": f"Bearer {creds.token}"}
        sent = 0
        with httpx.Client(timeout=10) as client:
            for device in tokens:
                body = {
                    "message": {
                        "token": device.token,
                        "data": {
                            "type": "new_order",
                            "order_id": str(order_id),
                            "customer_name": customer_name,
                            "total_cents": str(total_cents),
                        },
                        "notification": {
                            "title": f"New order #{order_id}",
                            "body": f"{customer_name} · €{total_cents / 100:.2f}",
                        },
                        "android": {
                            "priority": "HIGH",
                            "ttl": "180s",
                            "notification": {"channel_id": "new_orders", "sound": "default"},
                        },
                    }
                }
                try:
                    resp = client.post(url, json=body, headers=headers)
                except Exception as e:
                    logger.error(f"FCM send failed for device {device.id}: {e}")
                    continue
                if resp.status_code == 200:
                    sent += 1
                elif resp.status_code == 404 and "UNREGISTERED" in resp.text:
                    logger.info(f"Removing stale FCM token for device {device.id}")
                    db.delete(device)
                else:
                    logger.error(f"FCM error {resp.status_code} for device {device.id}: {resp.text[:200]}")
        db.commit()
        return sent
    finally:
        db.close()
