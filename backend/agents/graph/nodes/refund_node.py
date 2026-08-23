"""
Graph node: refund_node.

Destination for the "refund" route (refund_request intent). Scoped to
exactly one tool: check_refund_eligibility -- read-only by design (see
the tool's own docstring). This node can never cause a refund to
actually execute; it can only check eligibility and relay the standard
timeline message, or explain why the order isn't eligible yet.

Still uses the tool-calling loop pattern (rather than just calling the
function directly) so the model can extract order_id from natural
language and phrase the final response naturally -- same reasoning as
knowledge_node needing the LLM to phrase an answer from retrieved chunks.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import logger
from backend.db.models import Customer
from backend.agents.graph.state import AgentState
from backend.agents.tools.refund_eligibility_tools import make_check_refund_eligibility_tool

REFUND_NODE_SYSTEM_PROMPT = """\
You help customers with refund questions. You have one tool,
check_refund_eligibility, which checks whether a refund can be issued for
an order and never actually issues one.

Rules:
- If the customer hasn't given an order_id, ask for it.
- Never claim that a refund has been processed or that money has moved --
  you can only confirm eligibility and relay the standard timeline.
- If not eligible, explain why in plain terms (e.g. the return hasn't
  been completed yet, no payment was found, or a refund was already
  issued).
Keep your final answer concise and natural.
"""

MAX_TOOL_ITERATIONS = 2  # one tool, one likely call -- keep this tight


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- refund_node needs at least one.")


def make_refund_node(db: Session, current_user: Customer):
    """
    Builds the refund_node function, scoped to current_user. Register with
    graph.add_node("refund_node", make_refund_node(db, current_user)).
    """
    tools = [make_check_refund_eligibility_tool(db, current_user)]
    tools_by_name = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.2,
    ).bind_tools(tools)

    def _refund_node(state: AgentState) -> dict:
        question = _get_latest_human_message(state)
        messages = [SystemMessage(content=REFUND_NODE_SYSTEM_PROMPT), HumanMessage(content=question)]
        tool_call_trace = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = llm.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                logger.info(
                    "graph_node_refund_completed",
                    extra={
                        "customer_id": state["customer_id"],
                        "conversation_id": state["conversation_id"],
                        "tool_calls": [t["name"] for t in tool_call_trace],
                    },
                )
                return {
                    "messages": [AIMessage(content=response.content)],
                    "tool_calls": tool_call_trace,
                }

            for tool_call in response.tool_calls:
                tool = tools_by_name.get(tool_call["name"])
                result = tool.invoke(tool_call["args"]) if tool else {"error": f"Unknown tool: {tool_call['name']}"}
                tool_call_trace.append({"name": tool_call["name"], "args": tool_call["args"], "result": result})
                messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tool_call["id"]))

        logger.info(
            "graph_node_refund_hit_iteration_cap",
            extra={"customer_id": state["customer_id"], "conversation_id": state["conversation_id"]},
        )
        return {
            "messages": [AIMessage(content="I'm having trouble checking your refund status right now.")],
            "tool_calls": tool_call_trace,
            "escalated": True,
        }

    return _refund_node