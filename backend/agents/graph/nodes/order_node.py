"""
Graph node: order_node.

Destination for the "order" route (order_status intent). Unlike
knowledge_node, a single tool call isn't always right here -- "where's my
order" needs get_order, "has it shipped" needs track_shipment, "was I
charged" needs get_payment_status, and "what have I ordered recently"
needs list_orders. Rather than hardcoding one tool call, this node runs a
small SCOPED tool-calling loop (same idea as simple_agent.py, but
restricted to just these four tools) so the model picks the right one(s)
for the specific question.

FACTORY PATTERN, same reason as every tool: this node needs a real `db`
session and Customer object, which state doesn't carry (state only has
customer_id, a string, per the "never trust identity from state/model"
principle). So this is make_order_node(db, current_user) -> node
function, built fresh per request -- not a plain function LangGraph could
import and use directly.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import Customer
from backend.agents.graph.state import AgentState
from backend.agents.tools.order_tools import make_get_order_tool
from backend.agents.tools.list_order_tools import make_list_orders_tool
from backend.agents.tools.track_shipment_tools import make_track_shipment_tool
from backend.agents.tools.payment_status_tools import make_get_payment_status_tool

ORDER_NODE_SYSTEM_PROMPT = """\
You help customers with questions about their own orders -- status,
shipment tracking, and payment. Use the tools available to look up real
data; don't guess. If the customer hasn't given an order_id and you don't
know which order they mean, call list_orders first to find it, or ask
them directly if there are multiple recent orders it could be.
Keep your final answer concise and natural.
"""

MAX_TOOL_ITERATIONS = 3


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- order_node needs at least one.")


def make_order_node(db: Session, current_user: Customer):
    """
    Builds the order_node function, scoped to current_user via the same
    closure pattern as the tool factories. Returns a callable LangGraph
    can register with graph.add_node("order_node", make_order_node(db, current_user)).
    """
    tools = [
        make_get_order_tool(db, current_user),
        make_list_orders_tool(db, current_user),
        make_track_shipment_tool(db, current_user),
        make_get_payment_status_tool(db, current_user),
    ]
    tools_by_name = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.2,
    ).bind_tools(tools)

    def _order_node(state: AgentState) -> dict:
        question = _get_latest_human_message(state)
        messages = [SystemMessage(content=ORDER_NODE_SYSTEM_PROMPT), HumanMessage(content=question)]
        tool_call_trace = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = llm.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                
                return {
                    "messages": [AIMessage(content=response.content)],
                    "tool_calls": tool_call_trace,
                }

            for tool_call in response.tool_calls:
                tool = tools_by_name.get(tool_call["name"])
                result = tool.invoke(tool_call["args"]) if tool else {"error": f"Unknown tool: {tool_call['name']}"}
                tool_call_trace.append({"name": tool_call["name"], "args": tool_call["args"], "result": result})
                messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tool_call["id"]))

       
        return {
            "messages": [AIMessage(content="I'm having trouble finding that information right now.")],
            "tool_calls": tool_call_trace,
            "escalated": True,
        }

    return _order_node