import os
import sys

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, DeliveryStatus

def get_delivery_status(order_id: str) -> str:
    """Fetch live delivery status from PostgreSQL."""
    with app.app_context():
        shipment = DeliveryStatus.query.get(order_id)
        if shipment:
            return (f"Order ID: {shipment.order_id} | Carrier: {shipment.carrier} | "
                    f"Status: {shipment.transit_status} | Reason: {shipment.delay_reason} | "
                    f"Est. Delivery: {shipment.estimated_delivery}")
        return f"No delivery status found for Order ID {order_id}."

def update_delivery_status(order_id: str, new_status: str, delay_reason: str = "None") -> str:
    """Update delivery status directly in PostgreSQL in real time."""
    with app.app_context():
        shipment = DeliveryStatus.query.get(order_id)
        if shipment:
            shipment.transit_status = new_status
            shipment.delay_reason = delay_reason
            db.session.commit()
            return f"Updated delivery status for {order_id} to '{new_status}' in live database."
        return f"Order ID {order_id} not found in logistics system."