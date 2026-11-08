import os
import json
from groq import Groq
from sqlalchemy import func
from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus

def execute_tool_call(tool_name, tool_args):
    """
    Executes database reads and secure, role-restricted writes based on AI agent decisions.
    """
    try:
        if tool_name == "get_order_status":
            raw_order_id = tool_args.get("order_id", "").strip()
            clean_id = raw_order_id.upper().replace("-", "")

            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id
            ).first()
            
            if not stock and not delivery:
                return json.dumps({"status": "not_found", "message": f"No record found for order ID {raw_order_id}"})
            
            return json.dumps({
                "order_id": stock.order_id if stock else (delivery.order_id if delivery else raw_order_id),
                "item_name": stock.item_name if stock else "N/A",
                "dispatch_status": stock.dispatch_status if stock else "N/A",
                "hub_location": stock.hub_location if stock else "N/A",
                "carrier": delivery.carrier if delivery else "N/A",
                "transit_status": delivery.transit_status if delivery else "N/A",
                "delay_reason": delivery.delay_reason if delivery else "None",
                "estimated_delivery": delivery.estimated_delivery if delivery else "TBD"
            })

        elif tool_name == "request_order_cancellation":
            raw_order_id = tool_args.get("order_id", "").strip()
            reason = tool_args.get("reason", "Customer requested cancellation via Chatbot")
            clean_id = raw_order_id.upper().replace("-", "")

            stock = WarehouseStock.query.filter(
                func.upper(func.replace(WarehouseStock.order_id, '-', '')) == clean_id
            ).first()

            delivery = DeliveryStatus.query.filter(
                func.upper(func.replace(DeliveryStatus.order_id, '-', '')) == clean_id
            ).first()

            if not stock:
                return json.dumps({"status": "error", "message": f"Order {raw_order_id} not found."})

            # SECURE VALIDATION: Allow cancellation ONLY if item is still in warehouse processing state
            unshipped_statuses = ["Processing", "In Warehouse", "Pending"]
            if stock.dispatch_status in unshipped_statuses:
                stock.dispatch_status = "Cancelled"
                if delivery:
                    delivery.transit_status = "Cancelled"
                    delivery.delay_reason = reason
                
                db.session.commit()
                return json.dumps({"status": "success", "message": f"Order {stock.order_id} has been successfully cancelled."})
            else:
                # DENY DIRECT MUTATION: Order already shipped/delivered. Log a ticket instead.
                ticket = SupportTicket(
                    order_id=stock.order_id,
                    issue_description=f"Cancellation request denied (Order already '{stock.dispatch_status}'). Reason: {reason}",
                    priority="HIGH",
                    status="OPEN"
                )
                db.session.add(ticket)
                db.session.commit()
                return json.dumps({
                    "status": "denied",
                    "message": f"Cannot cancel order {stock.order_id} directly because its current status is '{stock.dispatch_status}'. A support ticket (ID: {ticket.id}) has been created for manual review."
                })

        elif tool_name == "create_support_ticket":
            order_id = tool_args.get("order_id", "GENERAL")
            issue_description = tool_args.get("issue_description")
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
            return json.dumps({"status": "error", "message": f"Unauthorized or unknown tool: {tool_name}"})

    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": "error", "message": str(e)})


def run_agent_workflow_with_logs(history, api_key):
    """
    Customer Assistant Agent Workflow with strict tool boundaries.
    """
    from app import app
    logs = []

    ACTIVE_MODEL = "openai/gpt-oss-20b"
    clean_api_key = api_key.strip() if api_key else ""

    with app.app_context():
        client = Groq(api_key=clean_api_key)
        logs.append(f"Initialized LLM client for model {ACTIVE_MODEL}.")

        # CUSTOMER-FACING TOOLS ONLY (NO DIRECT IN-TRANSIT / DELIVERED MUTATION TOOLS)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Retrieve current warehouse and delivery status for an order ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001 or ORD-500"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_order_cancellation",
                    "description": "Request cancellation for an order. Will only succeed if order has not been dispatched.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The unique order identifier"},
                            "reason": {"type": "string", "description": "Reason for cancellation request"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_support_ticket",
                    "description": "Create a support ticket for complaints, address change requests, or unresolved issues.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "Related order ID"},
                            "issue_description": {"type": "string", "description": "Detailed description of the issue"},
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
                    "You CAN: Check order statuses, request cancellations for unshipped orders, and open support tickets. "
                    "You CANNOT: Mark orders as 'Delivered', 'In Transit', or change internal hub logistics directly. "
                    "If a user asks to change delivery address or mark an order as delivered/in transit, open a support ticket for them."
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
                function_args = json.loads(tool_call.function.arguments)
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