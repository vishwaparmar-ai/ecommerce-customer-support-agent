"""
Graph node: return_node.

Destination for the "return" route (return_request intent). Same factory
pattern as order_node: needs a real db session + Customer, scoped via
closure, not available from state alone.

Scoped to exactly two tools: check_return_eligibility (read) and
create_return_request (write). The system prompt enforces the same rule
built into create_return_request's own tool description: check first,
only actually submit the return after the customer has explicitly agreed
to proceed -- this node doesn't add new enforcement, it just makes sure
that instruction is reinforced at the node level too, since this is a
fresh LLM call with its own message history, not a continuation of
order_node's conversation.
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
from backend.agents.tools.return_tools import (
    make_check_return_eligibility_tool,
    make_create_return_request_tool,
)

RETURN_NODE_SYSTEM_PROMPT = """\
You help customers return items they've ordered. You have two tools:

- check_return_eligibility: checks whether an order can be returned,
  without creating anything. Use this first, whenever a customer asks
  about returning something or whether they can return it.
- create_return_request: actually submits the return. Only call this
  AFTER the customer has explicitly confirmed they want to proceed with
  the return (after you've told them it's eligible and explained why, if
  relevant). Never call this on the first turn without an explicit yes
  from the customer in this conversation.

If the customer hasn't given an order_id, ask for it -- do not guess.
If a return isn't eligible, explain why in plain terms (e.g. window
expired, category not returnable, already delivered check failed).
Keep your final answer concise and natural.
"""

MAX_TOOL_ITERATIONS = 3


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- return_node needs at least one.")


def make_return_node(db: Session, current_user: Customer):
    """
    Builds the return_node function, scoped to current_user. Register with
    graph.add_node("return_node", make_return_node(db, current_user)).
    """
    tools = [
        make_check_return_eligibility_tool(db, current_user),
        make_create_return_request_tool(db, current_user),
    ]
    tools_by_name = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.2,
    ).bind_tools(tools)

    def _return_node(state: AgentState) -> dict:
        question = _get_latest_human_message(state)
        messages = [SystemMessage(content=RETURN_NODE_SYSTEM_PROMPT), HumanMessage(content=question)]
        tool_call_trace = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = llm.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                logger.info(
                    "graph_node_return_completed",
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
            "graph_node_return_hit_iteration_cap",
            extra={"customer_id": state["customer_id"], "conversation_id": state["conversation_id"]},
        )
        return {
            "messages": [AIMessage(content="I'm having trouble processing this return request right now.")],
            "tool_calls": tool_call_trace,
            "escalated": True,
        }

    return _return_node