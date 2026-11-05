import sqlite3
import os

WAREHOUSE_DB = os.path.join(os.path.dirname(__file__), '..', 'databases', 'warehouse.db')
LOGISTICS_DB = os.path.join(os.path.dirname(__file__), '..', 'databases', 'logistics.db')
TICKETS_DB = os.path.join(os.path.dirname(__file__), '..', 'databases', 'tickets.db')

def format_order_id(oid: str) -> str:
    if not oid:
        return "ORD-101"
    oid = str(oid).upper().strip()
    if oid.isdigit():
        return f"ORD-{oid}"
    if "ORD" in oid and not oid.startswith("ORD-"):
        return oid.replace("ORD", "ORD-")
    return oid

def send_automated_email(order_id: str, subject: str, body: str, recipient: str = "customer@example.com"):
    order_id = format_order_id(order_id)
    try:
        conn = sqlite3.connect(TICKETS_DB)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_emails (
                email_id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_email TEXT,
                ticket_id TEXT,
                order_id TEXT,
                subject TEXT,
                body TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            INSERT INTO sent_emails (recipient_email, ticket_id, order_id, subject, body)
            VALUES (?, ?, ?, ?, ?)
        ''', (recipient, "N/A", order_id, subject, body))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging email notification: {str(e)}")

def cancel_order(order_id: str, reason: str = "Customer requested cancellation") -> str:
    order_id = format_order_id(order_id)
    try:
        # 1. Update Logistics DB
        conn_l = sqlite3.connect(LOGISTICS_DB)
        cursor_l = conn_l.cursor()
        
        cursor_l.execute("SELECT transit_status FROM delivery_status WHERE order_id = ?", (order_id,))
        row = cursor_l.fetchone()

        if row:
            current_status = row[0]
            if current_status == "Delivered to Customer":
                conn_l.close()
                return f"Order {order_id} has already been delivered and cannot be cancelled."
            elif current_status == "Out for Delivery":
                conn_l.close()
                return f"Order {order_id} is currently Out for Delivery. Cancellation is locked."

        cursor_l.execute("UPDATE delivery_status SET transit_status = 'CANCELLED', delay_reason = ? WHERE order_id = ?", (f"Cancelled: {reason}", order_id))
        conn_l.commit()
        conn_l.close()

        # 2. Update Warehouse DB
        conn_w = sqlite3.connect(WAREHOUSE_DB)
        cursor_w = conn_w.cursor()
        cursor_w.execute("UPDATE warehouse_stock SET dispatch_status = 'CANCELLED' WHERE order_id = ?", (order_id,))
        conn_w.commit()
        conn_w.close()

        # 3. Trigger Email Notification
        email_subject = f"Order {order_id} Cancellation Confirmation"
        email_body = f"Hello,\n\nYour order '{order_id}' has been successfully CANCELLED.\n\nDetails:\n- Reason: {reason}\n- Refund: Initiated to original payment method (3–5 business days).\n\nThank you,\nProject Nexus Logistics Team"
        
        send_automated_email(order_id, email_subject, email_body)

        return f"SUCCESS: Order {order_id} cancelled successfully. Reason: {reason}. Email confirmation sent to inbox."
    except Exception as e:
        return f"Error cancelling order {order_id}: {str(e)}"

def update_delivery_address(order_id: str, new_address: str) -> str:
    order_id = format_order_id(order_id)
    try:
        conn = sqlite3.connect(LOGISTICS_DB)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(delivery_status)")
        columns = [col[1] for col in cursor.fetchall()]
        if "shipping_address" not in columns:
            cursor.execute("ALTER TABLE delivery_status ADD COLUMN shipping_address TEXT")

        cursor.execute("SELECT transit_status FROM delivery_status WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()

        if row and row[0] in ["Out for Delivery", "Delivered to Customer"]:
            conn.close()
            return f"Address update rejected: Order {order_id} is in '{row[0]}' state."

        cursor.execute("UPDATE delivery_status SET shipping_address = ? WHERE order_id = ?", (new_address, order_id))
        conn.commit()
        conn.close()

        email_subject = f"Delivery Address Update for Order {order_id}"
        email_body = f"Hello,\n\nThe shipping destination for Order '{order_id}' has been updated to:\n{new_address}\n\nThank you,\nProject Nexus Logistics Team"
        
        send_automated_email(order_id, email_subject, email_body)

        return f"SUCCESS: Address for order {order_id} updated to '{new_address}'. Confirmation email sent to inbox."
    except Exception as e:
        return f"Error updating address for {order_id}: {str(e)}"