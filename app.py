import sys
import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agents.nexus_orchestrator import run_agent_workflow_with_logs

app = Flask(__name__)

# Fetch GROQ_API_KEY securely from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

TICKETS_DB_PATH = os.path.join(os.path.dirname(__file__), 'databases', 'tickets.db')
WAREHOUSE_DB_PATH = os.path.join(os.path.dirname(__file__), 'databases', 'warehouse.db')
LOGISTICS_DB_PATH = os.path.join(os.path.dirname(__file__), 'databases', 'logistics.db')

# 1. CUSTOMER ROUTE
@app.route("/")
def index():
    return render_template("index.html")

# 2. CUSTOMER INBOX
@app.route("/inbox")
def customer_inbox():
    conn = sqlite3.connect(TICKETS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email_id, recipient_email, ticket_id, order_id, subject, body, sent_at FROM sent_emails ORDER BY sent_at DESC")
    emails = cursor.fetchall()
    conn.close()
    return render_template("inbox.html", emails=emails)

# 3. WAREHOUSE PORTAL (Receive & Hand off)
@app.route("/warehouse")
def warehouse_portal():
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, item_name, dispatch_status, hub_location FROM warehouse_stock ORDER BY order_id DESC")
    items = cursor.fetchall()
    conn.close()
    return render_template("warehouse.html", items=items)

@app.route("/warehouse/receive", methods=["POST"])
def warehouse_receive():
    order_id = request.form.get("order_id")
    item_name = request.form.get("item_name")
    hub_location = request.form.get("hub_location")

    if order_id and item_name:
        conn = sqlite3.connect(WAREHOUSE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO warehouse_stock (order_id, item_name, dispatch_status, hub_location) VALUES (?, ?, ?, ?)",
                       (order_id.upper(), item_name, "Received in Warehouse", hub_location))
        conn.commit()
        conn.close()

    return redirect(url_for("warehouse_portal"))

@app.route("/warehouse/dispatch", methods=["POST"])
def warehouse_dispatch():
    order_id = request.form.get("order_id")

    if order_id:
        # Update Warehouse DB status
        conn_w = sqlite3.connect(WAREHOUSE_DB_PATH)
        cursor_w = conn_w.cursor()
        cursor_w.execute("UPDATE warehouse_stock SET dispatch_status = 'Handed Over to Delivery' WHERE order_id = ?", (order_id,))
        conn_w.commit()
        conn_w.close()

        # Automatically insert into Delivery Partner Logistics DB
        conn_l = sqlite3.connect(LOGISTICS_DB_PATH)
        cursor_l = conn_l.cursor()
        cursor_l.execute("INSERT OR REPLACE INTO delivery_status (order_id, carrier, transit_status, delay_reason, estimated_delivery) VALUES (?, ?, ?, ?, ?)",
                         (order_id, "FastExpress", "Picked Up by Courier", "None", "2026-11-10"))
        conn_l.commit()
        conn_l.close()

    return redirect(url_for("warehouse_portal"))

# 4. DELIVERY PARTNER PORTAL
@app.route("/delivery")
def delivery_portal():
    conn = sqlite3.connect(LOGISTICS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, carrier, transit_status, delay_reason, estimated_delivery FROM delivery_status ORDER BY order_id DESC")
    shipments = cursor.fetchall()
    conn.close()
    return render_template("delivery.html", shipments=shipments)

@app.route("/delivery/update", methods=["POST"])
def delivery_update():
    order_id = request.form.get("order_id")
    status = request.form.get("transit_status")
    delay_reason = request.form.get("delay_reason") or "None"

    if order_id and status:
        conn = sqlite3.connect(LOGISTICS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE delivery_status SET transit_status = ?, delay_reason = ? WHERE order_id = ?", (status, delay_reason, order_id))
        conn.commit()
        conn.close()

    return redirect(url_for("delivery_portal"))

# 5. ADMIN QUEUE
@app.route("/admin")
def admin_dashboard():
    conn = sqlite3.connect(TICKETS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT ticket_id, order_id, customer_issue, priority, status, resolution_notes FROM support_tickets ORDER BY created_at DESC")
    tickets = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM support_tickets")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'OPEN'")
    open_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE priority = 'HIGH'")
    high_priority = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'RESOLVED'")
    resolved_count = cursor.fetchone()[0]
    conn.close()

    metrics = {"total": total, "open": open_count, "high_priority": high_priority, "resolved": resolved_count}
    return render_template("admin.html", tickets=tickets, metrics=metrics)

@app.route("/admin/resolve", methods=["POST"])
def resolve_ticket():
    ticket_id = request.form.get("ticket_id")
    notes = request.form.get("notes")

    if ticket_id and notes:
        conn = sqlite3.connect(TICKETS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE support_tickets SET status = 'RESOLVED', resolution_notes = ? WHERE ticket_id = ?", (notes, ticket_id))
        
        cursor.execute("SELECT order_id, customer_issue FROM support_tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        order_id = row[0] if row else "N/A"

        recipient = "customer@example.com"
        subject = f"Resolution Update for Support Ticket {ticket_id}"
        email_body = f"Hello,\n\nYour support ticket ({ticket_id}) regarding Order '{order_id}' has been resolved.\n\nResolution Details:\n{notes}\n\nThank you for choosing Project Nexus."

        cursor.execute("INSERT INTO sent_emails (recipient_email, ticket_id, order_id, subject, body) VALUES (?, ?, ?, ?, ?)",
                       (recipient, ticket_id, order_id, subject, email_body))
        conn.commit()
        conn.close()

    return redirect(url_for("admin_dashboard"))

# API ENDPOINT FOR CHATBOT
@app.route("/api/query", methods=["POST"])
def process_query():
    data = request.get_json()
    history = data.get("history", [])

    if not history:
        return jsonify({"status": "error", "response": "Empty message history."}), 400

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return jsonify({"status": "error", "response": "GROQ_API_KEY is not configured in system environment variables."}), 500

    try:
        agent_response, execution_logs = run_agent_workflow_with_logs(history, api_key)
        return jsonify({"status": "success", "response": agent_response, "logs": execution_logs})
    except Exception as e:
        return jsonify({"status": "error", "response": f"Server Error: {str(e)}", "logs": []}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)