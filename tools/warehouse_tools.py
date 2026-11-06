import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db
from models import WarehouseStock

def get_warehouse_stock(order_id: str) -> str:
    """Fetch live warehouse inventory status from PostgreSQL."""
    item = WarehouseStock.query.get(order_id)
    if item:
        return (f"Order ID: {item.order_id} | Item: {item.item_name} | "
                f"Dispatch Status: {item.dispatch_status} | Hub Location: {item.hub_location}")
    return f"No warehouse inventory record found for Order ID {order_id}."

def update_warehouse_status(order_id: str, new_status: str) -> str:
    """Update warehouse status in real-time."""
    item = WarehouseStock.query.get(order_id)
    if item:
        item.dispatch_status = new_status
        db.session.commit()
        return f"Updated warehouse status for {order_id} to '{new_status}'."
    return f"Order ID {order_id} not found in warehouse inventory."