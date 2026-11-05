import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'databases', 'warehouse.db')

def format_order_id(oid: str) -> str:
    if not oid:
        return "ORD-101"
    oid = str(oid).upper().strip()
    if oid.isdigit():
        return f"ORD-{oid}"
    if "ORD" in oid and not oid.startswith("ORD-"):
        return oid.replace("ORD", "ORD-")
    return oid

def query_warehouse_db(order_id: str) -> str:
    """Queries Warehouse SQLite DB for order stock, hub location, and dispatch status."""
    order_id = format_order_id(order_id)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, item_name, dispatch_status, hub_location FROM warehouse_stock WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return f"Warehouse DB Record:\n- Order ID: {row[0]}\n- Item Name: {row[1]}\n- Warehouse Status: {row[2]}\n- Hub Location: {row[3]}"
        else:
            return f"No warehouse record found for Order ID '{order_id}'."
    except Exception as e:
        return f"Error querying warehouse DB: {str(e)}"