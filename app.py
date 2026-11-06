import os
import sys
from flask import Flask, render_template, request, jsonify
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

# Bind SQLAlchemy to Flask app instance
db.init_app(app)

with app.app_context():
    db.create_all()
    
    # Seed sample delivery status records if empty
    if not DeliveryStatus.query.first():
        db.session.bulk_save_objects([
            DeliveryStatus(order_id="ORD1001", carrier="FedEx", transit_status="In Transit", delay_reason="None", estimated_delivery="2026-11-08"),
            DeliveryStatus(order_id="ORD1002", carrier="DHL", transit_status="Delayed", delay_reason="Severe Weather", estimated_delivery="2026-11-10"),
            DeliveryStatus(order_id="ORD1003", carrier="BlueDart", transit_status="Out for Delivery", delay_reason="None", estimated_delivery="2026-11-07")
        ])
        db.session.commit()

    # Seed sample warehouse records if empty
    if not WarehouseStock.query.first():
        db.session.bulk_save_objects([
            WarehouseStock(order_id="ORD1001", item_name="Logistics Controller Unit", dispatch_status="Dispatched", hub_location="Mumbai Hub A"),
            WarehouseStock(order_id="ORD1002", item_name="Sensors Pack x10", dispatch_status="Processing", hub_location="Bengaluru Hub C"),
            WarehouseStock(order_id="ORD1003", item_name="Industrial Router", dispatch_status="Ready for Pickup", hub_location="Delhi Hub B")
        ])
        db.session.commit()

# --- ROUTES ---

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

@app.route("/api/query", methods=["POST"])
def process_query():
    data = request.get_json()
    history = data.get("history", [])
    if not history:
        return jsonify({"status": "error", "response": "Empty message history."}), 400

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return jsonify({"status": "error", "response": "GROQ_API_KEY environment variable is missing."}), 500

    try:
        agent_response, execution_logs = run_agent_workflow_with_logs(history, api_key)
        return jsonify({"status": "success", "response": agent_response, "logs": execution_logs})
    except Exception as e:
        return jsonify({"status": "error", "response": f"Server Error: {str(e)}", "logs": []}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)