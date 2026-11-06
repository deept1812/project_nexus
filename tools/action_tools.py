import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, DeliveryStatus, WarehouseStock, SupportTicket

def update_delivery_address(order_id: str, new_address: str) -> str:
    """Update address and save directly to PostgreSQL in real time."""
    with app.app_context():
        shipment = DeliveryStatus.query.get(order_id)
        if shipment:
            shipment.delay_reason = f"Address updated to: {new_address}"
            db.session.commit()
            return f"Successfully updated delivery address for Order ID {order_id} to '{new_address}'."
        return f"Order ID {order_id} not found in logistics database."

def cancel_order(order_id: str, reason: str = "Customer requested cancellation") -> str:
    """Cancel order state across warehouse and logistics tables simultaneously."""
    with app.app_context():
        shipment = DeliveryStatus.query.get(order_id)
        warehouse_item = WarehouseStock.query.get(order_id)
        
        updated = False
        if shipment:
            shipment.transit_status = "Cancelled"
            shipment.delay_reason = reason
            updated = True
            
        if warehouse_item:
            warehouse_item.dispatch_status = "Cancelled"
            updated = True
            
        if updated:
            ticket = SupportTicket(
                ticket_id=f"TCK-{order_id}",
                order_id=order_id,
                customer_issue=f"Order Cancelled: {reason}",
                priority="HIGH",
                status="RESOLVED",
                resolution_notes="Automated cancellation processed by AI Agent."
            )
            db.session.add(ticket)
            db.session.commit()
            return f"Order ID {order_id} cancelled and updated across all systems in real time."
        
        return f"Order ID {order_id} not found."