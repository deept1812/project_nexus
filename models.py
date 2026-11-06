from extensions import db

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