import os
import sys
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy  # type: ignore[reportMissingImports]
from dotenv import load_dotenv

load_dotenv()

# Ensure internal modules in root can be imported cleanly
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from agents.nexus_orchestrator import run_agent_workflow_with_logs

app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
db_url = os.getenv("DATABASE_URL")

if db_url:
    # Convert standard postgres/postgresql URIs to explicit SQLAlchemy psycopg2 dialect
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    # Enforce SSL mode for cloud PostgreSQL connection (Render)
    if "?" not in db_url:
        db_url += "?sslmode=require"
else:
    # Local fallback sqlite database
    db_url = "sqlite:///nexus.db"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    ticket_id = db.Column(db.String(50), primary_key=True)
    order_id = db.Column(db.String(50))
    customer_issue = db.Column(db.Text)
    priority = db.Column(db.String(20))
    status = db.Column(db.String(20))
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class SentEmail(db.Model):
    __tablename__ = 'sent_emails'
    email_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    recipient_email = db.Column(db.String(120))
    ticket_id = db.Column(db.String(50))
    order_id = db.Column(db.String(50))
    subject = db.Column(db.String(200))
    body = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, server_default=db.func.now())

class WarehouseStock(db.Model):
    __tablename__ = 'warehouse_stock'
    order_id = db.Column(db.String(50), primary_key=True)
    item_name = db.Column(db.String(100))
    dispatch_status = db.Column(db.String(50))
    hub_location = db.Column(db.String(100))

class DeliveryStatus(db.Model):
    __tablename__ = 'delivery_status'
    order_id = db.Column(db.String(50), primary_key=True)
    carrier = db.Column(db.String(50))
    transit_status = db.Column(db.String(50))
    delay_reason = db.Column(db.String(100))
    estimated_delivery = db.Column(db.String(20))

# Initialize database schema automatically on boot
with app.app_context():
    db.create_all()

# --- APPLICATION ROUTES ---

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

# --- AI API ENDPOINT ---

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