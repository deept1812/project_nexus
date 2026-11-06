import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, SupportTicket, SentEmail

def create_support_ticket(order_id: str, issue_description: str, priority: str = "MEDIUM") -> str:
    """Create a new support ticket in cloud PostgreSQL database."""
    with app.app_context():
        ticket_id = f"TCK-{order_id}"
        existing = SupportTicket.query.get(ticket_id)
        if existing:
            existing.customer_issue = issue_description
            existing.priority = priority
            existing.status = "OPEN"
        else:
            ticket = SupportTicket(
                ticket_id=ticket_id,
                order_id=order_id,
                customer_issue=issue_description,
                priority=priority,
                status="OPEN",
                resolution_notes="Ticket initialized via AI Agent."
            )
            db.session.add(ticket)
        db.session.commit()
        return f"Support ticket created successfully with Ticket ID: {ticket_id}."

def send_customer_email(recipient_email: str, subject: str, body: str, order_id: str = "") -> str:
    """Log outgoing customer emails directly to PostgreSQL."""
    with app.app_context():
        email = SentEmail(
            recipient_email=recipient_email,
            ticket_id=f"TCK-{order_id}" if order_id else "GENERAL",
            order_id=order_id,
            subject=subject,
            body=body
        )
        db.session.add(email)
        db.session.commit()
        return f"Email sent and logged to customer inbox for {recipient_email}."