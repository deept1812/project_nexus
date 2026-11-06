import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, WarehouseStock

def get_warehouse_stock(order_id: str) -> str:
    """Fetch live warehouse inventory status from PostgreSQL."""
    with app.app_context():
        item = WarehouseStock.query.get(order_id)
        if item:
            return (f"Order ID: {item.order_id} | Item: {item.item_name} | "
                    f"Dispatch Status: {item.dispatch_status} | Hub: {item.hub_location}")
        return f"No warehouse inventory record found for Order ID {order_id}."

def update_warehouse_status(order_id: str, new_status: str) -> str:
    """Update warehouse status directly in PostgreSQL in real time."""
    with app.app_context():
        item = WarehouseStock.query.get(order_id)
        if item:
            item.dispatch_status = new_status
            db.session.commit()
            return f"Updated warehouse status for {order_id} to '{new_status}' in live database."
        return f"Order ID {order_id} not found in warehouse inventory."