import os
import json
from groq import Groq

# Import all PostgreSQL-connected tools
from tools.logistics_tools import get_delivery_status, update_delivery_status
from tools.warehouse_tools import get_warehouse_stock, update_warehouse_status
from tools.ticket_tools import create_support_ticket, send_customer_email
from tools.action_tools import update_delivery_address, cancel_order

# Tool Schema Definitions for Groq Function Calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_delivery_status",
            "description": "Fetch live delivery and shipment tracking status for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_warehouse_stock",
            "description": "Fetch warehouse inventory status and location details for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_delivery_address",
            "description": "Update the delivery address for an existing order in real time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001"},
                    "new_address": {"type": "string", "description": "The updated delivery address"}
                },
                "required": ["order_id", "new_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel an active order across logistics and warehouse systems.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g., ORD1001"},
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
            "description": "Escalate an issue by creating a support ticket in the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID"},
                    "issue_description": {"type": "string", "description": "Details of the issue"},
                    "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]}
                },
                "required": ["order_id", "issue_description"]
            }
        }
    }
]

# Mapping function names to Python functions
TOOL_MAP = {
    "get_delivery_status": get_delivery_status,
    "get_warehouse_stock": get_warehouse_stock,
    "update_delivery_address": update_delivery_address,
    "cancel_order": cancel_order,
    "create_support_ticket": create_support_ticket,
    "update_delivery_status": update_delivery_status,
    "update_warehouse_status": update_warehouse_status,
    "send_customer_email": send_customer_email
}

def run_agent_workflow_with_logs(message_history: list, api_key: str):
    """
    Executes the Groq AI Agent workflow with function calling, returning the final text answer and execution logs.
    """
    client = Groq(api_key=api_key)
    execution_logs = []

    # System prompt setting operational boundaries
    system_message = {
        "role": "system",
        "content": (
            "You are Project Nexus AI, an enterprise logistics and customer support assistant. "
            "You have access to live database tools to track, update, cancel, and escalate orders. "
            "Always query or modify data using your available tools when an Order ID is provided."
        )
    }

    full_messages = [system_message] + message_history

    # Initial LLM Call
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=full_messages,
        tools=TOOLS,
        tool_choice="auto"
    )

    response_message = response.choices[0].message

    # Process tool calls if requested by the model
    if response_message.tool_calls:
        full_messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            execution_logs.append(f"Executing Tool: {function_name} with args: {function_args}")
            
            if function_name in TOOL_MAP:
                tool_output = TOOL_MAP[function_name](**function_args)
            else:
                tool_output = f"Error: Tool '{function_name}' not implemented."
            
            execution_logs.append(f"Tool Result: {tool_output}")
            
            full_messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(tool_output)
            })

        # Second LLM call to generate natural language response using tool results
        second_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=full_messages
        )
        final_text = second_response.choices[0].message.content
    else:
        final_text = response_message.content

    return final_text, execution_logs