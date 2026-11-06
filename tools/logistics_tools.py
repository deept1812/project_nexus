import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db
from models import DeliveryStatus

def get_delivery_status(order_id: str) -> str:
    """Fetch live shipment tracking status from PostgreSQL."""
    shipment = DeliveryStatus.query.get(order_id)
    if shipment:
        return (f"Order ID: {shipment.order_id} | Carrier: {shipment.carrier} | "
                f"Status: {shipment.transit_status} | Reason: {shipment.delay_reason} | "
                f"Est. Delivery: {shipment.estimated_delivery}")
    return f"No shipment tracking record found for Order ID {order_id}."

def update_delivery_status(order_id: str, new_status: str, delay_reason: str = "None") -> str:
    """Update shipment status directly in PostgreSQL."""
    shipment = DeliveryStatus.query.get(order_id)
    if shipment:
        shipment.transit_status = new_status
        shipment.delay_reason = delay_reason
        db.session.commit()
        return f"Updated delivery status for {order_id} to '{new_status}'."
    return f"Order ID {order_id} not found in logistics system."