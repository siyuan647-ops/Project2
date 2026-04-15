"""Tool call logging decorator for hallucination audit trail."""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable

from app.context import get_conversation_id

logger = logging.getLogger(__name__)


def _extract_data_source(result: str, tool_name: str) -> str:
    """Extract data source identifier from tool result."""
    if "Polygon.io" in result or "polygon" in tool_name.lower():
        return "Polygon.io"
    elif "Yahoo Finance" in result or "yfinance" in tool_name.lower():
        return "Yahoo Finance"
    elif "Tavily" in result or "tavily" in tool_name.lower():
        return "Tavily"
    elif "DuckDuckGo" in result or "duckduckgo" in tool_name.lower():
        return "DuckDuckGo"
    return "unknown"


def logged_tool(tool_name: str):
    """Decorator that logs tool invocation to database.

    Args:
        tool_name: Name of the tool for identification
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            from app.storage import store

            start = time.time()

            # Get conversation_id from context (set by request handler)
            conversation_id = get_conversation_id() or 'unknown'
            message_id = None  # Message ID tracking can be added later

            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.time() - start) * 1000)
                data_source = _extract_data_source(result, tool_name)

                # Async fire-and-forget logging (skip if no valid conversation_id)
                if conversation_id and conversation_id != 'unknown':
                    try:
                        await store.log_tool_call(
                            conversation_id=conversation_id,
                            tool_name=tool_name,
                            tool_args={"args": str(args), "kwargs": dict(kwargs)},
                            tool_result=result,
                            data_source=data_source,
                            duration_ms=duration_ms,
                        )
                    except Exception as log_err:
                        logger.warning(f"Failed to log tool call: {log_err}")

                return result

            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                # Log error case (skip if no valid conversation_id)
                if conversation_id and conversation_id != 'unknown':
                    try:
                        await store.log_tool_call(
                            conversation_id=conversation_id,
                            tool_name=tool_name,
                            tool_args={"args": str(args), "kwargs": dict(kwargs)},
                            tool_result="",
                            data_source="error",
                            duration_ms=duration_ms,
                            status="error",
                            error_message=str(e),
                        )
                    except Exception:
                        pass
                raise

        return async_wrapper
    return decorator
