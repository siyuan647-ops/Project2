"""Prompt boundary utilities for safe user input handling.

This module provides functions to wrap and escape user input before
injecting it into LLM prompts, preventing prompt injection attacks.
"""

import re
from html import escape as html_escape


def escape_special_chars(text: str) -> str:
    """Escape special XML/HTML characters to prevent injection.

    Also breaks potential closing tags that could prematurely end
    the user input section.

    Args:
        text: Raw user input text

    Returns:
        Escaped text safe for embedding in XML-marked prompts
    """
    if not text:
        return ""

    # Break potential closing tag patterns by inserting zero-width space
    # This prevents users from injecting </user_input> to break out
    text = _break_closing_tags(text)

    # Use HTML escaping for XML special characters
    # escape() handles &, <, >, ", ' automatically
    return html_escape(text, quote=False)


def _break_closing_tags(text: str) -> str:
    """Break potential XML closing tag patterns.

    Inserts zero-width space (U+200B) after </ to prevent tag closure.
    """
    # Match </ followed by alphanumeric characters and >
    # Insert zero-width space to break the tag
    return re.sub(r"</(\w+)", r"<​/\1", text)


def wrap_user_input(text: str) -> str:
    """Wrap user input with XML boundary tags.

    The user input is escaped and wrapped in <user_input> tags to clearly
    delineate it from system instructions.

    Args:
        text: Raw user question or input

    Returns:
        XML-wrapped and escaped user input

    Example:
        >>> wrap_user_input("What is the price?")
        '<user_input>\nWhat is the price?\n</user_input>'
    """
    escaped = escape_special_chars(text)
    return f"<user_input>\n{escaped}\n</user_input>"


def wrap_historical_message(content: str, sender: str) -> str:
    """Wrap historical messages with XML boundary tags.

    Args:
        content: Message content
        sender: Message sender identifier

    Returns:
        XML-wrapped historical message
    """
    escaped_content = escape_special_chars(content)
    escaped_sender = escape_special_chars(sender)
    return f'<historical_message sender="{escaped_sender}">\n{escaped_content}\n</historical_message>'


def build_context_with_boundaries(messages: list[dict], max_chars: int = 6000) -> str:
    """Build conversation context with proper input boundaries.

    Replaces the raw _build_history_summary with boundary-aware version.

    Args:
        messages: List of message dictionaries with 'sender', 'content', 'event_type'
        max_chars: Maximum characters for the context

    Returns:
        XML-formatted context string
    """
    if not messages:
        return ""

    lines: list[str] = []
    total = 0

    for msg in reversed(messages):
        event_type = msg.get("event_type", "")
        sender = "user" if event_type == "user_message" else msg.get("sender", "unknown")
        content = msg.get("content", "")

        wrapped = wrap_historical_message(content, sender)

        if total + len(wrapped) > max_chars:
            lines.append("<!-- earlier messages omitted -->")
            break

        lines.append(wrapped)
        total += len(wrapped)

    lines.reverse()
    return "\n\n".join(lines)
