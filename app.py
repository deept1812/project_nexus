import os
import sys
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus
from agents.nexus_orchestrator import run_agent_workflow_with_logs

app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
db_url = os.getenv("DATABASE_URL")

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    if "?" not in db_url:
        db_url += "?sslmode=require"
else:
    db_url = "sqlite:///nexus.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Ensure database tables exist in PostgreSQL without populating hardcoded data
with app.app_context():
    db.create_all()

# --- WEB PORTAL ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/inbox")
def customer_inbox():
    emails = SentEmail.query.order_by(SentEmail.sent_at.desc()).all()
    return render_template("inbox.html", emails=emails)

@app.route("/warehouse")
def warehouse_portal():
    items = WarehouseStock.query.order_by(WarehouseStock.order_id.desc()).all()
    return render_template("warehouse.html", items=items)

@app.route("/delivery")
def delivery_portal():
    shipments = DeliveryStatus.query.order_by(DeliveryStatus.order_id.desc()).all()
    return render_template("delivery.html", shipments=shipments)

@app.route("/admin")
def admin_dashboard():
    tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
    metrics = {
        "total": SupportTicket.query.count(),
        "open": SupportTicket.query.filter_by(status='OPEN').count(),
        "high_priority": SupportTicket.query.filter_by(priority='HIGH').count(),
        "resolved": SupportTicket.query.filter_by(status='RESOLVED').count()
    }
    return render_template("admin.html", tickets=tickets, metrics=metrics)

# --- REAL-TIME DATABASE MUTATION ROUTES ---

@app.route("/warehouse/add", methods=["POST"])
def add_warehouse_item():
    """Form / API POST route to insert new items directly into PostgreSQL."""
    order_id = request.form.get("order_id") or request.json.get("order_id")
    item_name = request.form.get("item_name") or request.json.get("item_name")
    hub_location = request.form.get("hub_location") or request.json.get("hub_location")

    if not order_id or not item_name:
        return jsonify({"status": "error", "message": "Order ID and Item Name required"}), 400

    # Insert into WarehouseStock table
    new_item = WarehouseStock(
        order_id=order_id,
        item_name=item_name,
        dispatch_status="Processing",
        hub_location=hub_location or "Main Warehouse"
    )
    
    # Initialize parallel DeliveryStatus record
    new_shipment = DeliveryStatus(
        order_id=order_id,
        carrier="Pending Carrier",
        transit_status="In Warehouse",
        delay_reason="None",
        estimated_delivery="TBD"
    )

    db.session.merge(new_item)
    db.session.merge(new_shipment)
    db.session.commit()

    return redirect(url_for("warehouse_portal"))


@app.route("/warehouse/handoff/<order_id>", methods=["POST"])
def handoff_to_courier(order_id):
    """Update item status to indicate courier handoff across database tables."""
    item = WarehouseStock.query.get(order_id)
    shipment = DeliveryStatus.query.get(order_id)

    if item:
        item.dispatch_status = "Handed Over to Courier"
    if shipment:
        shipment.transit_status = "In Transit"

    db.session.commit()
    return redirect(url_for("warehouse_portal"))

# --- AI AGENT ENDPOINT ---

@app.route("/api/query", methods=["POST"])
def process_query():
    data = request.get_json()
    history = data.get("history", [])
    if not history:
        return jsonify({"status": "error", "response": "Empty message history."}), 400

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return jsonify({"status": "error", "response": "GROQ_API_KEY environment variable missing."}), 500

    try:
        agent_response, execution_logs = run_agent_workflow_with_logs(history, api_key)
        return jsonify({"status": "success", "response": agent_response, "logs": execution_logs})
    except Exception as e:
        return jsonify({"status": "error", "response": f"Server Error: {str(e)}", "logs": []}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)