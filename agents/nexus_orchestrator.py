import os
import json
from groq import Groq
from sqlalchemy import func
from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus

def execute_tool_call(tool_name, tool_args):
    """
    Executes database reads and customer requests with safe null checks and case-insensitivity.
    """
    try:
        if tool_name == "get_order_status":
            raw_order_id = (tool_args.get("order_id") or "").strip()
            if not raw_order_id:
                return json.dumps({"status": "error", "message": "Please provide an Order ID to check status."})

            clean_id = raw_order_id.upper().replace("-", "")

            # Flexible query across both tables
            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id
            ).first()
            
            if not stock and not delivery:
                return json.dumps({"status": "not_found", "message": f"No record found for order ID '{raw_order_id}'."})

            # Safe extraction of values whether row exists in Stock, Delivery, or both
            matched_id = stock.order_id if stock else delivery.order_id
            item_name = stock.item_name if stock else "N/A"
            dispatch_status = stock.dispatch_status if stock else "N/A"
            hub_location = stock.hub_location if stock else "N/A"
            
            carrier = delivery.carrier if (delivery and delivery.carrier) else "Pending Carrier"
            transit_status = delivery.transit_status if (delivery and delivery.transit_status) else "N/A"
            delay_reason = delivery.delay_reason if (delivery and delivery.delay_reason) else "None"
            estimated_delivery = delivery.estimated_delivery if (delivery and delivery.estimated_delivery) else "TBD"

            return json.dumps({
                "order_id": matched_id,
                "item_name": item_name,
                "dispatch_status": dispatch_status,
                "hub_location": hub_location,
                "carrier": carrier,
                "transit_status": transit_status,
                "delay_reason": delay_reason,
                "estimated_delivery": estimated_delivery
            })

        elif tool_name == "request_order_cancellation":
            raw_order_id = (tool_args.get("order_id") or "").strip()
            if not raw_order_id:
                return json.dumps({"status": "need_order_id", "message": "Ask the user to specify which Order ID they want to cancel."})

            reason = tool_args.get("reason", "Customer requested cancellation via Chatbot")
            clean_id = raw_order_id.upper().replace("-", "")

            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id
            ).first()

            if not stock and not delivery:
                return json.dumps({"status": "error", "message": f"Order '{raw_order_id}' not found in database."})

            # Check dispatch state safely
            current_status = stock.dispatch_status if stock else (delivery.transit_status if delivery else "Unknown")
            unshipped_statuses = ["Processing", "In Warehouse", "Pending"]

            if current_status in unshipped_statuses:
                if stock:
                    stock.dispatch_status = "Cancelled"
                if delivery:
                    delivery.transit_status = "Cancelled"
                    delivery.delay_reason = reason
                
                db.session.commit()
                order_ref = stock.order_id if stock else delivery.order_id
                return json.dumps({"status": "success", "message": f"Order {order_ref} has been successfully cancelled."})
            else:
                order_ref = stock.order_id if stock else delivery.order_id
                ticket = SupportTicket(
                    order_id=order_ref,
                    issue_description=f"Cancellation request denied (Current status is '{current_status}'). Reason: {reason}",
                    priority="HIGH",
                    status="OPEN"
                )
                db.session.add(ticket)
                db.session.commit()
                return json.dumps({
                    "status": "denied",
                    "message": f"Cannot cancel order {order_ref} directly because it is already '{current_status}'. A support ticket (ID: {ticket.id}) was opened for review."
                })

        elif tool_name == "create_support_ticket":
            order_id = tool_args.get("order_id", "GENERAL")
            issue_description = tool_args.get("issue_description", "General support request")
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
    Main orchestrator function executing customer queries with strict error-trapping.
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
                    "description": "Retrieve current status and tracking details for an order ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001 or ord100"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_order_cancellation",
                    "description": "Request order cancellation. Only works if item is unshipped.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID to cancel"},
                            "reason": {"type": "string", "description": "Reason for cancellation"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_support_ticket",
                    "description": "Create a support ticket for complaints or assistance.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "Related order ID"},
                            "issue_description": {"type": "string", "description": "Description of the request"},
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
                    "You are Nexus AI, a real-time logistics customer support assistant. "
                    "When looking up an order status or cancellation request, extract the order ID provided by the user and call the appropriate tool."
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