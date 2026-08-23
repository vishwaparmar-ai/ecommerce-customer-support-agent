"""
Graph node: escalation_node.

Destination for the "escalation" route (support_other intent, or
state["escalated"] set True by another node hitting its iteration cap).
Scoped to escalate_to_human and create_support_ticket -- both tools
already have descriptions that distinguish "hand off now" vs "log for
later", so this node's system prompt just reinforces that distinction
rather than re-deriving it.

Note: when this node is reached because another node set escalated=True
(e.g. order_node or return_node hit MAX_TOOL_ITERATIONS), state["intent"]
still reflects the ORIGINAL intent (order/return/etc), not "escalation" --
route_by_intent checks state["escalated"] first specifically so this can
happen. This node should use state["intent"] plus the latest message to
write a sensible escalation reason, not assume the customer literally
asked for a human.
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
from backend.agents.tools.human_escalation_tool import make_escalate_to_human_tool
from backend.agents.tools.create_support_ticket_tools import make_create_support_ticket_tool

ESCALATION_NODE_SYSTEM_PROMPT = """\
You handle cases that need human involvement. You have two tools:

- escalate_to_human: hands this off to a human agent RIGHT NOW. Use this
  when the customer explicitly asked for a human, seems frustrated, or
  the situation is ambiguous/sensitive/couldn't be resolved automatically.
- create_support_ticket: logs an issue for later, non-urgent review. Use
  this only if escalate_to_human clearly doesn't fit -- e.g. a minor
  suggestion or a question that doesn't need an immediate human response.

When calling either tool, write a clear, honest reason/summary based on
what the customer actually said -- don't invent details. After calling a
tool, tell the customer plainly what happens next (a human will follow up
soon; do not promise a specific timeframe you don't actually know).
"""

MAX_TOOL_ITERATIONS = 2


def _get_latest_human_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    raise ValueError("No HumanMessage found in state -- escalation_node needs at least one.")


def make_escalation_node(db: Session, current_user: Customer):
    """
    Builds the escalation_node function, scoped to current_user. Register
    with graph.add_node("escalation_node", make_escalation_node(db, current_user)).
    """
    tools = [
        make_escalate_to_human_tool(db, current_user),
        make_create_support_ticket_tool(db, current_user),
    ]
    tools_by_name = {t.name: t for t in tools}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.2,
    ).bind_tools(tools)

    def _escalation_node(state: AgentState) -> dict:
        question = _get_latest_human_message(state)
        context_note = f"(Note: this conversation was originally about '{state.get('intent')}'.)"
        messages = [
            SystemMessage(content=ESCALATION_NODE_SYSTEM_PROMPT),
            HumanMessage(content=f"{question}\n\n{context_note}"),
        ]
        tool_call_trace = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = llm.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                logger.info(
                    "graph_node_escalation_completed",
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

        # Even the escalation path failing shouldn't leave the customer
        # with nothing -- fall back to a plain, honest message.
        logger.info(
            "graph_node_escalation_hit_iteration_cap",
            extra={"customer_id": state["customer_id"], "conversation_id": state["conversation_id"]},
        )
        return {
            "messages": [AIMessage(content="I'm connecting you with a support agent who can help further.")],
            "tool_calls": tool_call_trace,
        }

    return _escalation_node