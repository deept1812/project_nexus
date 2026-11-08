import os
import json
from groq import Groq
from extensions import db
from models import SupportTicket, SentEmail, WarehouseStock, DeliveryStatus

def execute_tool_call(tool_name, tool_args):
    """
    Executes database reads and writes dynamically based on the AI agent's tool decisions.
    Uses SQLAlchemy 2.0 compliant db.session.get() methods.
    """
    try:
        if tool_name == "get_order_status":
            order_id = tool_args.get("order_id")
            stock = db.session.get(WarehouseStock, order_id)
            delivery = db.session.get(DeliveryStatus, order_id)
            
            if not stock and not delivery:
                return json.dumps({"status": "not_found", "message": f"No record found for order ID {order_id}"})
            
            return json.dumps({
                "order_id": order_id,
                "item_name": stock.item_name if stock else "N/A",
                "dispatch_status": stock.dispatch_status if stock else "N/A",
                "hub_location": stock.hub_location if stock else "N/A",
                "carrier": delivery.carrier if delivery else "N/A",
                "transit_status": delivery.transit_status if delivery else "N/A",
                "delay_reason": delivery.delay_reason if delivery else "None",
                "estimated_delivery": delivery.estimated_delivery if delivery else "TBD"
            })

        elif tool_name == "update_order_status":
            order_id = tool_args.get("order_id")
            new_status = tool_args.get("new_status")
            reason = tool_args.get("reason", "Updated via AI Agent")

            stock = db.session.get(WarehouseStock, order_id)
            delivery = db.session.get(DeliveryStatus, order_id)

            if stock:
                stock.dispatch_status = new_status
            if delivery:
                delivery.transit_status = new_status
                delivery.delay_reason = reason

            db.session.commit()
            return json.dumps({"status": "success", "message": f"Order {order_id} updated to {new_status} in PostgreSQL."})

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
            return json.dumps({"status": "error", "message": f"Unknown tool name: {tool_name}"})

    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": "error", "message": str(e)})


def run_agent_workflow_with_logs(history, api_key):
    """
    Main orchestrator function executing Groq LLM queries and PostgreSQL tools.
    """
    from app import app
    logs = []

    # Active recommended Groq production model for tool calling
    ACTIVE_MODEL = "llama-3.1-8b-instant"

    # Clean API Key to eliminate trailing spaces/newlines
    clean_api_key = api_key.strip() if api_key else ""

    with app.app_context():
        client = Groq(api_key=clean_api_key)
        logs.append("Initialized Groq client inside Flask app context.")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "Retrieve current warehouse and delivery tracking details for an order ID.",
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
                    "name": "update_order_status",
                    "description": "Update warehouse or delivery status for an order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The unique order identifier"},
                            "new_status": {"type": "string", "description": "New status (e.g. Cancelled, Delayed, In Transit, Delivered)"},
                            "reason": {"type": "string", "description": "Reason for status change"}
                        },
                        "required": ["order_id", "new_status"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_support_ticket",
                    "description": "Create a support ticket for a customer complaint.",
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
                    "You are Nexus AI, a real-time logistics and warehouse support assistant. "
                    "Help users check order status, update delivery progress, cancel orders, or log support tickets."
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