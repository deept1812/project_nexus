import os
import sys
import json
import traceback
import urllib.request
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from sqlalchemy import text, func, or_

# Load environment variables
load_dotenv(override=True)

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from extensions import db
from models import User, SupportTicket, SentEmail, WarehouseStock, DeliveryStatus
from agents.nexus_orchestrator import run_agent_workflow_with_logs

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "nexus_production_secret_key_9988776655")

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

# Schema creation and migration on app startup
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            # Fix Issue 2: Ensure support_tickets table exists with ID column
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL,
                    issue_description TEXT NOT NULL,
                    priority VARCHAR(20) DEFAULT 'MEDIUM',
                    status VARCHAR(20) DEFAULT 'OPEN',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    phone VARCHAR(20),
                    otp_code VARCHAR(6),
                    is_verified BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_code VARCHAR(6);"))
            conn.execute(text("ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS recipient VARCHAR(120);"))
            conn.execute(text("ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS subject VARCHAR(200);"))
            conn.execute(text("ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS body TEXT;"))
            conn.execute(text("ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
            conn.execute(text("ALTER TABLE warehouse_stock ADD COLUMN IF NOT EXISTS customer_email VARCHAR(120);"))
            conn.execute(text("ALTER TABLE warehouse_stock ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(20);"))
            conn.execute(text("ALTER TABLE delivery_status ADD COLUMN IF NOT EXISTS customer_email VARCHAR(120);"))
            conn.execute(text("ALTER TABLE delivery_status ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(20);"))
            conn.commit()
    except Exception as e:
        print(f"Migration Notice: {e}")

# --- AUTHENTICATION & LOGIN ROUTES ---

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        role = request.form.get("role")

        # Fix Issue 1: Enforce strict role-to-credential matching
        role_credentials = {
            "admin": ("admin", "admin123"),
            "warehouse": ("warehouse1", "wh123"),
            "delivery": ("delivery1", "del123")
        }

        if role in role_credentials:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            expected_user, expected_pass = role_credentials[role]

            if username == expected_user and password == expected_pass:
                session["user_role"] = role
                session["username"] = username

                if role == "warehouse":
                    return redirect(url_for("warehouse_portal"))
                elif role == "delivery":
                    return redirect(url_for("delivery_portal"))
                elif role == "admin":
                    return redirect(url_for("admin_dashboard"))
            else:
                return render_template("login.html", error=f"Invalid credentials for {role.capitalize()} Portal.")

    return render_template("login.html")

@app.route("/phone-login-verify", methods=["POST"])
def phone_login_verify():
    try:
        data = request.get_json() or {}
        user_json_url = data.get("user_json_url")

        if not user_json_url:
            return jsonify({"status": "error", "message": "Missing verification URL"}), 400

        req = urllib.request.Request(user_json_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            user_data = json.loads(response.read().decode('utf-8'))

        country_code = user_data.get("user_country_code", "")
        phone_number = user_data.get("user_phone_number", "")
        full_phone = f"{country_code}{phone_number}"

        if not phone_number:
            return jsonify({"status": "error", "message": "Failed to fetch verified phone number"}), 400

        user = User.query.filter_by(phone=full_phone).first()
        if not user:
            user = User(
                email=f"phone_{phone_number[-4:]}@nexus.com",
                phone=full_phone
            )
            db.session.add(user)
            db.session.commit()

        session["user_role"] = "customer"
        session["user_phone"] = full_phone
        session["user_email"] = user.email

        return jsonify({"status": "success", "message": "Authenticated successfully", "phone": full_phone})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# --- WEB PORTAL DISPLAY ROUTES ---

@app.route("/customer")
def customer_app():
    user_phone = session.get("user_phone", "")
    user_email = session.get("user_email", "")

    if not user_phone and not user_email:
        return redirect(url_for("login_page"))

    orders = []
    if user_phone or user_email:
        orders = WarehouseStock.query.filter(
            or_(
                func.lower(func.coalesce(WarehouseStock.customer_phone, '')) == user_phone.lower(),
                func.lower(func.coalesce(WarehouseStock.customer_email, '')) == user_email.lower()
            )
        ).order_by(WarehouseStock.order_id.desc()).all()

    return render_template("index.html", orders=orders, user_phone=user_phone, user_email=user_email)

@app.route("/inbox")
def customer_inbox():
    if session.get("user_role") not in ["customer", "admin"]:
        return redirect(url_for("login_page"))

    emails = SentEmail.query.order_by(SentEmail.sent_at.desc()).all()
    return render_template("inbox.html", emails=emails)

@app.route("/warehouse")
def warehouse_portal():
    if session.get("user_role") not in ["warehouse", "admin"]:
        return redirect(url_for("login_page"))

    items = WarehouseStock.query.order_by(WarehouseStock.order_id.desc()).all()
    return render_template("warehouse.html", items=items)

@app.route("/delivery")
def delivery_portal():
    if session.get("user_role") not in ["delivery", "admin"]:
        return redirect(url_for("login_page"))

    shipments = DeliveryStatus.query.order_by(DeliveryStatus.order_id.desc()).all()
    return render_template("delivery.html", shipments=shipments)

@app.route("/admin")
def admin_dashboard():
    if session.get("user_role") != "admin":
        return redirect(url_for("login_page"))

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
    if session.get("user_role") not in ["warehouse", "admin"]:
        return redirect(url_for("login_page"))

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
    if session.get("user_role") not in ["warehouse", "admin"]:
        return redirect(url_for("login_page"))

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
    if session.get("user_role") not in ["delivery", "admin"]:
        return redirect(url_for("login_page"))

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
    if session.get("user_role") != "admin":
        return redirect(url_for("login_page"))

    ticket = db.session.get(SupportTicket, ticket_id)
    if ticket:
        ticket.status = "RESOLVED"
        db.session.commit()
    return redirect(url_for("admin_dashboard"))

# --- GROQ AI AGENT ENDPOINT ---

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