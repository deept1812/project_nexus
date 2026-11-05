import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'databases', 'logistics.db')

def format_order_id(oid: str) -> str:
    if not oid:
        return "ORD-101"
    oid = str(oid).upper().strip()
    if oid.isdigit():
        return f"ORD-{oid}"
    if "ORD" in oid and not oid.startswith("ORD-"):
        return oid.replace("ORD", "ORD-")
    return oid

def query_logistics_db(order_id: str) -> str:
    """Queries Delivery Partner SQLite DB for tracking status, carrier info, and delay reasons."""
    order_id = format_order_id(order_id)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(delivery_status)")
        columns = [col[1] for col in cursor.fetchall()]
        has_address = "shipping_address" in columns

        if has_address:
            cursor.execute("SELECT order_id, carrier, transit_status, delay_reason, estimated_delivery, shipping_address FROM delivery_status WHERE order_id = ?", (order_id,))
        else:
            cursor.execute("SELECT order_id, carrier, transit_status, delay_reason, estimated_delivery FROM delivery_status WHERE order_id = ?", (order_id,))
            
        row = cursor.fetchone()
        conn.close()

        if row:
            address_str = f"\n- Delivery Address: {row[5]}" if has_address and len(row) > 5 and row[5] else ""
            return f"Logistics DB Record:\n- Order ID: {row[0]}\n- Carrier: {row[1]}\n- Transit Status: {row[2]}\n- Delay Reason: {row[3]}\n- Estimated Delivery: {row[4]}{address_str}"
        else:
            return f"No logistics tracking record found for Order ID '{order_id}'."
    except Exception as e:
        return f"Error querying logistics DB: {str(e)}"