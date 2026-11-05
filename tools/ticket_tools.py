import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'databases', 'tickets.db')

def create_support_ticket(order_id: str, issue_description: str, priority: str = "HIGH") -> str:
    """Creates an escalated support ticket in the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM support_tickets")
        count = cursor.fetchone()[0] + 1
        ticket_id = f"TCK-{1000 + count}"

        cursor.execute('''
            INSERT INTO support_tickets (ticket_id, order_id, customer_issue, priority, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticket_id, order_id, issue_description, priority.upper(), "OPEN"))

        conn.commit()
        conn.close()

        return f"Support ticket created successfully! Ticket ID: {ticket_id} | Status: OPEN | Priority: {priority.upper()}"
    except Exception as e:
        return f"Error creating support ticket: {str(e)}"

def check_ticket_status(ticket_id: str) -> str:
    """Queries tickets.db to fetch ticket status and resolution notes for the customer."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT ticket_id, order_id, customer_issue, priority, status, resolution_notes FROM support_tickets WHERE ticket_id = ?", (ticket_id.upper(),))
        row = cursor.fetchone()
        conn.close()

        if row:
            t_id, order_id, issue, priority, status, notes = row
            resolution_text = notes if notes else "Ticket is currently open and being reviewed by our support team."
            return f"Ticket Summary for {t_id}:\n- Order ID: {order_id}\n- Issue: {issue}\n- Status: {status}\n- Resolution Notes: {resolution_text}"
        else:
            return f"Ticket ID '{ticket_id}' was not found in our system."
    except Exception as e:
        return f"Error fetching ticket status: {str(e)}"