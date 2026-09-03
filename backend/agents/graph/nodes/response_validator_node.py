"""
Graph node: response_validator.

Final validation layer before the response reaches the customer.

The validator must be defensive because LLM message content can be either:

    str
    list[dict]
    list[str]
    or another structured content representation.

It must NEVER crash while validating a response.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from backend.core.logging import logger
from backend.agents.graph.state import AgentState


SAFE_FALLBACK_MESSAGE = (
    "Something went wrong while preparing your response. "
    "I'm connecting you with a support agent to make sure this is handled correctly."
)


ACTION_CLAIM_PHRASES = [
    "has been cancelled",
    "order is cancelled",
    "refund has been issued",
    "refund will be processed",
    "return has been submitted",
    "return request has been created",
]


WRITE_TOOL_NAMES = {
    "cancel_order",
    "create_return_request",
    "create_support_ticket",
    "escalate_to_human",
}


def _extract_text_content(content: Any) -> str:
    """
    Safely convert LangChain message content into plain text.

    LLM providers can return content as either:

        "some text"

    or:

        [
            {"type": "text", "text": "some text"}
        ]

    or:

        [
            "some text",
            {"type": "text", "text": "more text"}
        ]

    The validator only needs the textual portion.
    """

    if content is None:
        return ""

    # ---------------------------------------------------------
    # Normal string response
    # ---------------------------------------------------------

    if isinstance(content, str):
        return content.strip()

    # ---------------------------------------------------------
    # Structured/list response
    # ---------------------------------------------------------

    if isinstance(content, list):

        text_parts: list[str] = []

        for item in content:

            # Example:
            # {"type": "text", "text": "Hello"}
            if isinstance(item, dict):

                text = item.get("text")

                if isinstance(text, str):
                    text_parts.append(text)

                continue

            # Example:
            # ["Hello", "World"]
            if isinstance(item, str):
                text_parts.append(item)

        return " ".join(text_parts).strip()

    # ---------------------------------------------------------
    # Unknown content type.
    #
    # Do NOT convert arbitrary objects/dicts to strings because
    # that could make internal structured data look like a
    # legitimate customer-facing response.
    # ---------------------------------------------------------

    return ""


def _tool_call_succeeded(
    tool_calls: list[dict],
) -> bool:
    """
    Check whether a consequential write tool succeeded.
    """

    for call in tool_calls:

        if call.get("name") not in WRITE_TOOL_NAMES:
            continue

        result = call.get("result", {})

        if isinstance(result, dict) and "error" not in result:
            return True

    return False


def response_validator_node(
    state: AgentState,
) -> dict:

    messages = state.get("messages", [])

    # ---------------------------------------------------------
    # No messages
    # ---------------------------------------------------------

    if not messages:

        logger.info(
            "response_validator_no_messages",
            extra={
                "customer_id": state["customer_id"],
            },
        )

        return {
            "messages": [
                AIMessage(
                    content=SAFE_FALLBACK_MESSAGE
                )
            ],
            "escalated": True,
        }

    # ---------------------------------------------------------
    # Extract response text safely
    # ---------------------------------------------------------

    last_message = messages[-1]

    content = _extract_text_content(
        last_message.content
    )

    # ---------------------------------------------------------
    # Check 1: Empty response
    # ---------------------------------------------------------

    if not content:

        logger.info(
            "response_validator_empty_response",
            extra={
                "customer_id": state["customer_id"],
                "content_type": type(
                    last_message.content
                ).__name__,
            },
        )

        return {
            "messages": [
                AIMessage(
                    content=SAFE_FALLBACK_MESSAGE
                )
            ],
            "escalated": True,
        }

    # ---------------------------------------------------------
    # Check 2: Raw leaked data/error
    # ---------------------------------------------------------

    if (
        content.startswith("{")
        or "'error':" in content
        or '"error":' in content
    ):

        logger.info(
            "response_validator_leaked_raw_data",
            extra={
                "customer_id": state["customer_id"],
                "content_preview": content[:100],
            },
        )

        return {
            "messages": [
                AIMessage(
                    content=SAFE_FALLBACK_MESSAGE
                )
            ],
            "escalated": True,
        }

    # ---------------------------------------------------------
    # Check 3: Unverified consequential action
    # ---------------------------------------------------------

    content_lower = content.lower()

    claims_action = any(
        phrase in content_lower
        for phrase in ACTION_CLAIM_PHRASES
    )

    if claims_action and not _tool_call_succeeded(
        state.get("tool_calls", [])
    ):

        logger.info(
            "response_validator_unverified_action_claim",
            extra={
                "customer_id": state["customer_id"],
                "content_preview": content[:100],
                "tool_calls": [
                    tool.get("name")
                    for tool in state.get(
                        "tool_calls",
                        [],
                    )
                ],
            },
        )

        return {
            "messages": [
                AIMessage(
                    content=SAFE_FALLBACK_MESSAGE
                )
            ],
            "escalated": True,
        }

    # ---------------------------------------------------------
    # Everything passed
    # ---------------------------------------------------------

    return {}