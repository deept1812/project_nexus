import sys
import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.warehouse_tools import query_warehouse_db
from tools.logistics_tools import query_logistics_db
from tools.ticket_tools import create_support_ticket, check_ticket_status
from tools.action_tools import cancel_order, update_delivery_address, format_order_id

TOOL_MAP = {
    "query_warehouse_db": query_warehouse_db,
    "query_logistics_db": query_logistics_db,
    "create_support_ticket": create_support_ticket,
    "check_ticket_status": check_ticket_status,
    "cancel_order": cancel_order,
    "update_delivery_address": update_delivery_address
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_warehouse_db",
            "description": "Queries Warehouse SQLite DB for stock and dispatch status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. ORD-105"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_logistics_db",
            "description": "Queries Delivery Partner SQLite DB for transit status and carrier info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. ORD-105"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancels an active shipment ONLY after user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. ORD-105"},
                    "reason": {"type": "string", "description": "Reason for cancellation"}
                },
                "required": ["order_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_delivery_address",
            "description": "Updates shipping address in logistics DB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID, e.g. ORD-105"},
                    "new_address": {"type": "string", "description": "Full new delivery address"}
                },
                "required": ["order_id", "new_address"]
            }
        }
    }
]

SYSTEM_INSTRUCTION = """
You are Project Nexus, an AI-Powered Multi-Agent Logistics Orchestrator.

OFFICIAL CONTACT INFO:
- Helpline: 1-800-NEXUS-HELP (1-800-639-8743)
- Support Email: support@nexus.logistics

STRICT CANCELLATION SUCCESS OUTPUT FORMAT:
When `cancel_order` returns success, output the confirmation using EXACT HTML break tags so each bullet point is on a separate line:

✅ <strong>Cancellation Successful</strong><br><br>Your order <strong><ORDER_ID></strong> has been successfully cancelled.<br><br>• <strong>Status:</strong> CANCELLED<br>• <strong>Reason:</strong> <CANCELLATION_REASON><br>• <strong>Refund:</strong> Initiated to your original payment method (3–5 business days)<br>• <strong>Confirmation:</strong> A receipt has been sent to your <strong>Mail Inbox</strong>.<br><br>Is there anything else I can help you with?

MULTI-STEP CANCELLATION WORKFLOW:
1. PHASE 1 (Reason Selection):
   Query `query_logistics_db`. If eligible, output interactive reason buttons.

2. PHASE 2 (Feedback Form):
   Show an inline HTML text area (max 500 words, optional).

3. PHASE 3 (Final Confirmation):
   Ask for final confirmation:
   "<div class='options-panel'>
     <button class='opt-btn opt-danger' onclick=\"sendOption('FINAL CONFIRMATION: YES, cancel ORD-xxx')\">YES, Confirm Cancellation</button>
     <button class='opt-btn' onclick=\"sendOption('NO, keep my order ORD-xxx')\">NO, Keep My Order</button>
   </div>"

4. PHASE 4 (Execution):
   ONLY when user clicks 'FINAL CONFIRMATION: YES...', invoke `cancel_order` and output the strict HTML format above.
"""

def resolve_tool_name(raw_name: str) -> str:
    clean = raw_name.lower().replace(" ", "_").replace("-", "_")
    if "warehouse" in clean:
        return "query_warehouse_db"
    if "logistics" in clean or "logistic" in clean or "delivery" in clean:
        return "query_logistics_db"
    if "cancel" in clean:
        return "cancel_order"
    if "address" in clean:
        return "update_delivery_address"
    return clean

def clean_response_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'```json[\s\S]*?```', '', text)
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)
    cleaned = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', cleaned)
    return cleaned.strip()

def run_agent_workflow_with_logs(conversation_history: list, api_key: str = None):
    # Retrieve key from parameters or load from system environment
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY is not set. Please specify it in your .env file or environment settings.")

    client = Groq(api_key=key)
    logs = []

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + conversation_history
    last_user_msg = conversation_history[-1]['content'] if conversation_history else ""

    try:
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.2
        )
    except Exception as e:
        logs.append(f"Fallback triggered: {str(e)}")
        fallback_response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=messages,
            temperature=0.2
        )
        return clean_response_text(fallback_response.choices[0].message.content), logs

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        messages.append(response_message)

        for tool_call in tool_calls:
            func_name = resolve_tool_name(tool_call.function.name)
            
            try:
                func_args = json.loads(tool_call.function.arguments)
            except Exception:
                func_args = {}

            if "order_id" in func_args and func_args["order_id"]:
                func_args["order_id"] = format_order_id(func_args["order_id"])

            logs.append(f"Executing Tool: `{func_name}` with args `{func_args}`")

            if func_name in TOOL_MAP:
                if func_name == "cancel_order":
                    is_final = any(k in last_user_msg.lower() for k in ["final confirmation: yes", "yes, cancel", "confirm cancellation"])
                    if not is_final:
                        oid = func_args.get("order_id", "ORD-105")
                        if "selected reason" in last_user_msg.lower() or "reason for" in last_user_msg.lower():
                            tool_output = f"SYSTEM GUARDRAIL: Output Phase 2 feedback form for {oid}."
                        else:
                            tool_output = f"SYSTEM GUARDRAIL: Output Phase 1 reason buttons for {oid}."
                    else:
                        tool_output = TOOL_MAP[func_name](
                            order_id=func_args.get("order_id", ""),
                            reason=func_args.get("reason", "Customer cancelled after confirmation")
                        )
                elif func_name == "update_delivery_address":
                    tool_output = TOOL_MAP[func_name](
                        order_id=func_args.get("order_id", ""),
                        new_address=func_args.get("new_address", "")
                    )
                else:
                    tool_output = TOOL_MAP[func_name](func_args.get("order_id", ""))

                logs.append(f"Tool Output: `{tool_output}`")
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": func_name,
                    "content": tool_output
                })

        synthesis_response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=messages,
            temperature=0.2
        )
        return clean_response_text(synthesis_response.choices[0].message.content), logs

    raw_content = response_message.content or ""
    clean_text = clean_response_text(raw_content)

    match = re.search(r'ORD-\d+|\b10[1-9]\b', last_user_msg, re.IGNORECASE)
    if match and not tool_calls:
        oid = format_order_id(match.group(0))
        w_data = query_warehouse_db(oid)
        l_data = query_logistics_db(oid)
        
        messages.append({"role": "system", "content": f"LIVE DB DATA FOR {oid}:\nWarehouse: {w_data}\nLogistics: {l_data}\nFormat this into a clean markdown summary using explicit line breaks."})
        
        synth = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=messages,
            temperature=0.1
        )
        return clean_response_text(synth.choices[0].message.content), logs

    return clean_text, logs