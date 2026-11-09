from extensions import db
from datetime import datetime

class WarehouseStock(db.Model):
    __tablename__ = 'warehouse_stock'
    order_id = db.Column(db.String(50), primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    dispatch_status = db.Column(db.String(50), default='Processing')
    hub_location = db.Column(db.String(100), default='Main Warehouse')
    customer_email = db.Column(db.String(120), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)

class DeliveryStatus(db.Model):
    __tablename__ = 'delivery_status'
    order_id = db.Column(db.String(50), primary_key=True)
    carrier = db.Column(db.String(50), default='Pending Carrier')
    transit_status = db.Column(db.String(50), default='In Warehouse')
    delay_reason = db.Column(db.String(255), default='None')
    estimated_delivery = db.Column(db.String(50), default='TBD')
    customer_email = db.Column(db.String(120), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(50), nullable=False)
    issue_description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='MEDIUM')
    status = db.Column(db.String(20), default='OPEN')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SentEmail(db.Model):
    __tablename__ = 'sent_emails'
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)