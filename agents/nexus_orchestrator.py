import os
import json
from groq import Groq
from sqlalchemy import func, or_
from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus

def execute_tool_call(tool_name, tool_args):
    """
    Executes customer-specific identity-verified database reads and requests.
    Enforces strict mapping between Order ID and customer email/phone.
    """
    try:
        if tool_name == "get_order_status":
            raw_order_id = (tool_args.get("order_id") or "").strip()
            auth_contact = (tool_args.get("customer_email_or_phone") or "").strip().lower()

            if not raw_order_id:
                return json.dumps({"status": "need_order_id", "message": "Please provide your Order ID."})

            if not auth_contact:
                return json.dumps({"status": "need_auth", "message": "Please provide your registered Email or Phone number to verify identity."})

            clean_id = raw_order_id.upper().replace("-", "")

            # Look up order in database matching BOTH Order ID and Customer Email/Phone
            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id,
                or_(
                    func.lower(func.coalesce(WarehouseStock.customer_email, '')) == auth_contact,
                    func.lower(func.coalesce(WarehouseStock.customer_phone, '')) == auth_contact
                )
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id,
                or_(
                    func.lower(func.coalesce(DeliveryStatus.customer_email, '')) == auth_contact,
                    func.lower(func.coalesce(DeliveryStatus.customer_phone, '')) == auth_contact
                )
            ).first()

            # If no match found, check if order exists under a different customer account
            if not stock and not delivery:
                existing_order = WarehouseStock.query.filter(
                    func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id
                ).first()

                if existing_order:
                    return json.dumps({
                        "status": "access_denied",
                        "message": f"Access Denied: The contact information '{auth_contact}' is not authorized to view Order '{raw_order_id}'."
                    })
                
                return json.dumps({"status": "not_found", "message": f"No order found with ID '{raw_order_id}'."})

            matched_id = stock.order_id if stock else delivery.order_id
            return json.dumps({
                "status": "verified",
                "order_id": matched_id,
                "customer_email": stock.customer_email if stock else delivery.customer_email,
                "item_name": stock.item_name if stock else "N/A",
                "dispatch_status": stock.dispatch_status if stock else "N/A",
                "hub_location": stock.hub_location if stock else "N/A",
                "carrier": delivery.carrier if (delivery and delivery.carrier) else "Pending Carrier",
                "transit_status": delivery.transit_status if (delivery and delivery.transit_status) else "N/A",
                "delay_reason": delivery.delay_reason if (delivery and delivery.delay_reason) else "None",
                "estimated_delivery": delivery.estimated_delivery if (delivery and delivery.estimated_delivery) else "TBD"
            })

        elif tool_name == "request_order_cancellation":
            raw_order_id = (tool_args.get("order_id") or "").strip()
            auth_contact = (tool_args.get("customer_email_or_phone") or "").strip().lower()
            reason = tool_args.get("reason", "Customer requested cancellation via Chatbot")

            if not raw_order_id or not auth_contact:
                return json.dumps({"status": "need_auth", "message": "Both Order ID and registered Email/Phone are required for cancellation."})

            clean_id = raw_order_id.upper().replace("-", "")

            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id,
                or_(
                    func.lower(func.coalesce(WarehouseStock.customer_email, '')) == auth_contact,
                    func.lower(func.coalesce(WarehouseStock.customer_phone, '')) == auth_contact
                )
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id,
                or_(
                    func.lower(func.coalesce(DeliveryStatus.customer_email, '')) == auth_contact,
                    func.lower(func.coalesce(DeliveryStatus.customer_phone, '')) == auth_contact
                )
            ).first()

            if not stock and not delivery:
                return json.dumps({"status": "access_denied", "message": "Access Denied: Customer contact details do not match order records."})

            current_status = stock.dispatch_status if stock else delivery.transit_status
            unshipped_statuses = ["Processing", "In Warehouse", "Pending"]

            if current_status in unshipped_statuses:
                if stock:
                    stock.dispatch_status = "Cancelled"
                if delivery:
                    delivery.transit_status = "Cancelled"
                    delivery.delay_reason = reason
                
                recipient_email = stock.customer_email if (stock and stock.customer_email) else auth_contact
                email_log = SentEmail(
                    recipient=recipient_email,
                    subject=f"Cancellation Confirmed: Order {raw_order_id}",
                    body=f"Hello,\n\nYour order {raw_order_id} has been cancelled successfully.\nReason: {reason}\n\nProject Nexus Support"
                )
                db.session.add(email_log)
                db.session.commit()

                return json.dumps({"status": "success", "message": f"Order {raw_order_id} cancelled. Confirmation sent to {recipient_email}."})
            else:
                order_ref = stock.order_id if stock else delivery.order_id
                ticket = SupportTicket(
                    order_id=order_ref,
                    issue_description=f"Cancellation denied (Status is '{current_status}'). Reason: {reason}",
                    priority="HIGH",
                    status="OPEN"
                )
                db.session.add(ticket)
                db.session.commit()
                return json.dumps({"status": "denied", "message": f"Cannot cancel order {order_ref} directly because it is '{current_status}'. Ticket #{ticket.id} generated."})

        elif tool_name == "create_support_ticket":
            order_id = tool_args.get("order_id", "GENERAL")
            issue_description = tool_args.get("issue_description", "General customer support request")
            priority = tool_args.get("priority", "MEDIUM")

            ticket = SupportTicket(
                order_id=order_id,
                issue_description=issue_description,
                priority=priority,
                status="OPEN"
            )
            db.session.add(ticket)
            db.session.commit()

            return json.dumps({"status": "success", "ticket_id": ticket.id, "message": "Support ticket generated successfully."})

        else:
            return json.dumps({"status": "error", "message": f"Unauthorized tool request: {tool_name}"})

    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": "error", "message": str(e)})


def run_agent_workflow_with_logs(history, api_key):
    """
    Main orchestrator function executing customer queries with strict error-trapping and contact auth.
    """
    from app import app
    logs = []

    ACTIVE_MODEL = "openai/gpt-oss-20b"
    clean_api_key = api_key.strip() if api_key else ""

    with app.app_context():
        client = Groq(api_key=clean_api_key)
        logs.append(f"Initialized LLM client for model {ACTIVE_MODEL}.")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Retrieve order tracking details. Requires customer email or phone for verification.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001"},
                            "customer_email_or_phone": {"type": "string", "description": "Registered email address or phone number"}
                        },
                        "required": ["order_id", "customer_email_or_phone"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_order_cancellation",
                    "description": "Cancel an order. Requires customer email or phone verification.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID"},
                            "customer_email_or_phone": {"type": "string", "description": "Registered email or phone number"},
                            "reason": {"type": "string", "description": "Cancellation reason"}
                        },
                        "required": ["order_id", "customer_email_or_phone"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_support_ticket",
                    "description": "Create a support ticket for complaints or address changes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "Related order ID"},
                            "issue_description": {"type": "string", "description": "Description of issue"},
                            "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"], "description": "Priority level"}
                        },
                        "required": ["issue_description"]
                    }
                }
            }
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Nexus AI, a secure logistics customer assistant. "
                    "SECURITY RULE: ALWAYS demand both Order ID and customer Email/Phone before providing order details. "
                    "If the email or phone number doesn't match the order, politely deny access."
                )
            }
        ]

        for msg in history:
            sender = msg.get("sender") or msg.get("role")
            role = "user" if sender in ["user", "human"] else "assistant"
            text = msg.get("text") or msg.get("content", "")
            if text:
                messages.append({"role": role, "content": text})

        response = client.chat.completions.create(
            model=ACTIVE_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            messages.append(response_message)
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments or "{}")
                tool_output = execute_tool_call(function_name, function_args)

                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": tool_output
                })

            final_response = client.chat.completions.create(
                model=ACTIVE_MODEL,
                messages=messages
            )
            return final_response.choices[0].message.content, logs

        return response_message.content, logs