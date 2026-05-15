import logging
import socket

from app.config import settings

logger = logging.getLogger(__name__)


def print_order(order):
    """Send order to Epson receipt printer via ESC/POS over TCP."""
    if not settings.printer_enabled:
        logger.info(f"Printing disabled, skipping order #{order.id}")
        return

    try:
        from escpos.printer import Network

        printer = Network(settings.printer_ip, port=settings.printer_port)

        printer.set(align="center", bold=True, double_height=True)
        printer.text("ORDER\n")
        printer.text(f"#{order.id}\n\n")

        printer.set(align="left", bold=False, double_height=False)
        printer.text(f"Customer: {order.customer_name}\n")
        printer.text(f"Phone: {order.customer_phone}\n")
        printer.text(f"Pickup: {order.expected_pickup_time}\n")
        printer.text("-" * 32 + "\n")

        for item in order.items:
            printer.set(bold=True)
            printer.text(f"{item.quantity}x {item.item_name}\n")
            printer.set(bold=False)
            for mod in item.modifiers:
                printer.text(f"   + {mod.modifier_name}\n")
            if item.special_notes:
                printer.text(f"   Note: {item.special_notes}\n")

        printer.text("-" * 32 + "\n")
        printer.set(align="right")
        printer.text(f"Total: ${order.subtotal_cents / 100:.2f}\n")

        if order.pickup_notes:
            printer.text("\n")
            printer.set(align="left")
            printer.text(f"Notes: {order.pickup_notes}\n")

        printer.cut()
        printer.close()
        logger.info(f"Order #{order.id} printed successfully")

    except (socket.error, OSError) as e:
        logger.error(f"Printer connection failed for order #{order.id}: {e}")
    except Exception as e:
        logger.error(f"Print failed for order #{order.id}: {e}")
