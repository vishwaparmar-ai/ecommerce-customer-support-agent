"""
Graph node: response_validator.

Final step every path routes through before END (per the doc's section 12
workflow diagram). A plain function, not a factory -- it only inspects
state, it doesn't need db/current_user, since it isn't calling any tool
or service itself.

What it actually checks (deliberately practical, not exhaustive):
    1. The response isn't empty/whitespace -- a node returning nothing
       usable shouldn't reach the customer silently.
    2. The response isn't a raw leaked dict/error (a node forgot to
       phrase a natural-language message and a tool result or exception
       string leaked through as-is).
    3. The response doesn't CLAIM a consequential action happened
       ("your order has been cancelled", "your refund has been issued")
       without a matching successful tool call actually being present in
       state["tool_calls"] this turn. This is the most valuable check --
       it catches the LLM hallucinating that it did something it didn't.

On any failure, this REPLACES the last message with a safe fallback and
sets escalated=True, rather than letting a bad response reach the
customer. It does not raise -- a validator that crashes is worse than one
that's occasionally overcautious.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from backend.core.logging import logger
from backend.agents.graph.state import AgentState

SAFE_FALLBACK_MESSAGE = (
    "Something went wrong while preparing your response. "
    "I'm connecting you with a support agent to make sure this is handled correctly."
)

# Phrases that claim a consequential action was completed. Kept small and
# specific rather than trying to catch every possible phrasing -- false
# negatives here are safer than false positives that escalate everything.
ACTION_CLAIM_PHRASES = [
    "has been cancelled",
    "order is cancelled",
    "refund has been issued",
    "refund will be processed",
    "return has been submitted",
    "return request has been created",
]

# Tool names whose successful execution would justify the corresponding
# claim above. Kept as one combined set since any successful write this
# turn is grounds for an action-claim to be plausible.
WRITE_TOOL_NAMES = {"cancel_order", "create_return_request", "create_support_ticket", "escalate_to_human"}


def _tool_call_succeeded(tool_calls: list[dict]) -> bool:
    """A tool call 'succeeded' if its result dict doesn't contain an error key."""
    for call in tool_calls:
        if call.get("name") in WRITE_TOOL_NAMES:
            result = call.get("result", {})
            if isinstance(result, dict) and "error" not in result:
                return True
    return False


def response_validator_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    if not messages:
        logger.info("response_validator_no_messages", extra={"customer_id": state["customer_id"]})
        return {"messages": [AIMessage(content=SAFE_FALLBACK_MESSAGE)], "escalated": True}

    last_message = messages[-1]
    content = (last_message.content or "").strip()

    # Check 1: empty response.
    if not content:
        logger.info("response_validator_empty_response", extra={"customer_id": state["customer_id"]})
        return {"messages": [AIMessage(content=SAFE_FALLBACK_MESSAGE)], "escalated": True}

    # Check 2: raw leaked dict/error.
    if content.startswith("{") or "'error':" in content or '"error":' in content:
        logger.info(
            "response_validator_leaked_raw_data",
            extra={"customer_id": state["customer_id"], "content_preview": content[:100]},
        )
        return {"messages": [AIMessage(content=SAFE_FALLBACK_MESSAGE)], "escalated": True}

    # Check 3: hallucinated action claim without a matching successful tool call.
    content_lower = content.lower()
    claims_action = any(phrase in content_lower for phrase in ACTION_CLAIM_PHRASES)
    if claims_action and not _tool_call_succeeded(state.get("tool_calls", [])):
        logger.info(
            "response_validator_unverified_action_claim",
            extra={
                "customer_id": state["customer_id"],
                "content_preview": content[:100],
                "tool_calls": [t.get("name") for t in state.get("tool_calls", [])],
            },
        )
        return {"messages": [AIMessage(content=SAFE_FALLBACK_MESSAGE)], "escalated": True}

    # All checks passed -- let the response through unchanged.
    return {}