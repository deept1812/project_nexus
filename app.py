import os
import sys
import traceback
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv

load_dotenv(override=True)

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus
from agents.nexus_orchestrator import run_agent_workflow_with_logs

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "nexus_super_secret_session_key_123")

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

with app.app_context():
    db.create_all()

# --- AUTHENTICATION & LOGIN ROUTES ---

@app.route("/")
def home():
    """Default landing page opens the Portal Authentication view."""
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        role = request.form.get("role")
        
        # 1. Customer OTP Verification
        if role == "customer":
            email = request.form.get("email", "").strip().lower()
            otp = request.form.get("otp", "").strip()
            
            if email and (otp == "1234" or len(otp) == 4):
                session["user_role"] = "customer"
                session["user_email"] = email
                return redirect(url_for("customer_app"))
            else:
                return render_template("login.html", error="Invalid OTP Code. Use 1234 for testing.")

        # 2. Staff Password Verification (Admin, Warehouse, Delivery)
        elif role in ["warehouse", "delivery", "admin"]:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            # Default Staff Credentials
            credentials = {
                "admin": "admin123",
                "warehouse1": "wh123",
                "delivery1": "del123"
            }

            if username in credentials and credentials[username] == password:
                session["user_role"] = role
                session["username"] = username

                if role == "warehouse":
                    return redirect(url_for("warehouse_portal"))
                elif role == "delivery":
                    return redirect(url_for("delivery_portal"))
                elif role == "admin":
                    return redirect(url_for("admin_dashboard"))
            else:
                return render_template("login.html", error=f"Invalid credentials for {role.capitalize()} Login.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# --- WEB PORTAL DISPLAY ROUTES ---

@app.route("/customer")
def customer_app():
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

# --- REAL-TIME POSTGRESQL MUTATION ROUTES ---

@app.route("/warehouse/add", methods=["POST"])
def add_warehouse_item():
    order_id = (request.form.get("order_id") or "").strip()
    item_name = (request.form.get("item_name") or "").strip()
    hub_location = (request.form.get("hub_location") or "Main Warehouse").strip()
    customer_email = (request.form.get("customer_email") or "").strip().lower()
    customer_phone = (request.form.get("customer_phone") or "").strip()

    if not order_id or not item_name:
        return jsonify({"status": "error", "message": "Order ID and Item Name required"}), 400

    new_item = WarehouseStock(
        order_id=order_id,
        item_name=item_name,
        dispatch_status="Processing",
        hub_location=hub_location,
        customer_email=customer_email,
        customer_phone=customer_phone
    )
    
    new_shipment = DeliveryStatus(
        order_id=order_id,
        carrier="Pending Carrier",
        transit_status="In Warehouse",
        delay_reason="None",
        estimated_delivery="TBD",
        customer_email=customer_email,
        customer_phone=customer_phone
    )

    db.session.merge(new_item)
    db.session.merge(new_shipment)
    db.session.commit()

    return redirect(url_for("warehouse_portal"))

@app.route("/warehouse/handoff/<order_id>", methods=["POST"])
def handoff_to_courier(order_id):
    order_id = order_id.strip()
    item = db.session.get(WarehouseStock, order_id)
    shipment = db.session.get(DeliveryStatus, order_id)

    if item:
        item.dispatch_status = "Handed Over to Courier"
    
    if shipment:
        shipment.transit_status = "In Transit"
        if shipment.carrier == "Pending Carrier":
            shipment.carrier = "FedEx Express"
    else:
        new_shipment = DeliveryStatus(
            order_id=order_id,
            carrier="FedEx Express",
            transit_status="In Transit",
            delay_reason="None",
            estimated_delivery="Within 3 Days",
            customer_email=item.customer_email if item else None,
            customer_phone=item.customer_phone if item else None
        )
        db.session.add(new_shipment)

    db.session.commit()
    return redirect(url_for("warehouse_portal"))

@app.route("/delivery/update", methods=["POST"])
def update_delivery():
    order_id = request.form.get("order_id", "").strip()
    status = request.form.get("transit_status", "").strip()
    delay_reason = request.form.get("delay_reason", "").strip() or "None"

    shipment = db.session.get(DeliveryStatus, order_id)
    stock = db.session.get(WarehouseStock, order_id)

    if shipment:
        shipment.transit_status = status
        shipment.delay_reason = delay_reason

    if stock and status in ["Delivered", "Cancelled"]:
        stock.dispatch_status = status

    db.session.commit()
    return redirect(url_for("delivery_portal"))

@app.route("/admin/resolve/<int:ticket_id>", methods=["POST"])
def resolve_ticket(ticket_id):
    ticket = db.session.get(SupportTicket, ticket_id)
    if ticket:
        ticket.status = "RESOLVED"
        db.session.commit()
    return redirect(url_for("admin_dashboard"))

# --- AI AGENT ENDPOINT ---

@app.route("/api/query", methods=["POST"])
def process_query():
    data = request.get_json() or {}
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
        traceback.print_exc()
        return jsonify({"status": "error", "response": f"Server Error: {str(e)}", "logs": []}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)