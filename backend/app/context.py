"""Request context for passing conversation_id through the call stack.

Uses contextvars to store per-request state that doesn't need to be
passed explicitly through every function call.
"""

from contextvars import ContextVar
from typing import Optional

# Current conversation ID for tool call logging
conversation_id_ctx: ContextVar[str] = ContextVar("conversation_id", default="")


def get_conversation_id() -> str:
    """Get the current conversation ID from context.

    Returns:
        The conversation ID if set, empty string otherwise.
    """
    return conversation_id_ctx.get()


def set_conversation_id(conv_id: str) -> None:
    """Set the current conversation ID in context.

    Args:
        conv_id: The conversation ID to set.
    """
    conversation_id_ctx.set(conv_id)
