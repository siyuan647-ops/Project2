"""Memory compression pipeline - Sliding Window + LLM summarization.

When conversation exceeds threshold, old messages are compressed into a summary
and archived, keeping only the most recent N turns in raw form.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.storage import store
from app.routing.embeddings import get_embedding_service
from app.utils.prompt_boundary import wrap_historical_message

if TYPE_CHECKING:
    from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)

# Configuration
MAX_WINDOW_SIZE = 8  # Keep last 8 turns in raw form
COMPRESSION_THRESHOLD = 8  # Trigger compression every 8 turns


async def check_and_compress_memory(conversation_id: str) -> bool:
    """Check if memory compression is needed and execute if so.

    Returns True if compression was performed.
    """
    try:
        # Get current message count
        latest_turn = await store.get_latest_turn(conversation_id)

        # Get last compressed turn
        last_compressed = await store.get_last_compressed_turn(conversation_id)

        # Calculate how many turns need compression
        # We always keep MAX_WINDOW_SIZE most recent turns uncompressed
        turns_to_compress = latest_turn - last_compressed - MAX_WINDOW_SIZE

        if turns_to_compress < COMPRESSION_THRESHOLD:
            logger.debug(
                f"No compression needed for {conversation_id}: "
                f"latest={latest_turn}, last_compressed={last_compressed}, "
                f"to_compress={turns_to_compress}"
            )
            return False

        logger.info(
            f"Compressing memory for {conversation_id}: "
            f"turns {last_compressed + 1} to {latest_turn - MAX_WINDOW_SIZE}"
        )

        # Get messages to compress
        messages = await store.get_messages_in_range(
            conversation_id,
            start_turn=last_compressed + 1,
            end_turn=latest_turn - MAX_WINDOW_SIZE
        )

        if not messages:
            logger.warning(f"No messages found to compress for {conversation_id}")
            await store.update_last_compressed_turn(conversation_id, latest_turn - MAX_WINDOW_SIZE)
            return False

        # Generate summary using LLM
        summary = await generate_llm_summary(conversation_id, messages)

        # Save summary
        summary_result = await store.save_summary(
            conversation_id=conversation_id,
            content=summary,
            summary_type="compressed_history",
            turn_range=f"{last_compressed + 1}-{latest_turn - MAX_WINDOW_SIZE}",
            message_count=len(messages),
        )

        # Generate and save embedding for the summary
        emb_service = get_embedding_service()
        embedding = emb_service.encode(summary)
        if embedding:
            await store.update_summary_embedding(summary_result["id"], embedding)

        # Update last compressed turn
        await store.update_last_compressed_turn(conversation_id, latest_turn - MAX_WINDOW_SIZE)

        logger.info(
            f"Memory compression complete for {conversation_id}: "
            f"compressed {len(messages)} messages into summary {summary_result['id']}"
        )

        return True

    except Exception as e:
        logger.exception(f"Memory compression failed for {conversation_id}: {e}")
        return False


async def generate_llm_summary(conversation_id: str, messages: list[dict]) -> str:
    """Generate a concise summary of conversation history using LLM.

    Args:
        conversation_id: The conversation ID
        messages: List of messages to summarize

    Returns:
        A concise summary (300-500 characters) highlighting key points
    """
    from app.agents.llm_config import get_model_client

    # Build context text from messages with boundaries
    context_parts = []
    for msg in messages:
        sender = "user" if msg.get("event_type") == "user_message" else msg.get("sender", "unknown")
        content = msg.get("content", "")[:400]  # Truncate long messages
        context_parts.append(wrap_historical_message(content, sender))

    context = "\n\n".join(context_parts)

    # Prepare prompt for LLM
    prompt = f"""请对以下投资分析对话进行摘要，提取关键信息：

对话历史：
{context}

摘要要求：
1. 用户关注的主要股票和分析维度（如PE、营收、新闻等）
2. 用户明确表达的投资偏好或风格
3. 关键财务数据和投资建议结论
4. 用户提出的重要问题或关注点

请用简洁的中文总结（200-400字），使用第三人称客观描述："""

    try:
        client = get_model_client()

        # Import here to avoid circular dependency
        from autogen_core.models import UserMessage

        result = await client.create([UserMessage(content=prompt, source="summarizer")])
        summary = result.content.strip()

        # Validate summary length
        if len(summary) < 50:
            # Fallback to heuristic summary if LLM returns something too short
            summary = generate_heuristic_summary(messages)

        return summary

    except Exception as e:
        logger.error(f"LLM summary generation failed: {e}, using heuristic fallback")
        return generate_heuristic_summary(messages)


def generate_heuristic_summary(messages: list[dict]) -> str:
    """Generate a simple heuristic summary when LLM is unavailable.

    This is a fallback that concatenates the most important parts of messages.
    """
    lines = []
    total_chars = 0
    max_chars = 500

    # Process messages in reverse (most recent first)
    for msg in reversed(messages):
        sender = msg.get("sender", "Unknown")
        content = msg.get("content", "")[:200]  # First 200 chars

        line = f"{sender}: {content}"

        if total_chars + len(line) > max_chars:
            break

        lines.append(line)
        total_chars += len(line)

    lines.reverse()  # Restore chronological order

    return "对话摘要：\n" + "\n".join(lines)


async def get_compressed_context(
    conversation_id: str,
    include_summaries: bool = True,
    include_recent: bool = True,
) -> dict:
    """Get the compressed memory context for a conversation.

    Returns a dict with:
        - summaries: List of compressed summaries
        - recent_messages: List of recent (uncompressed) messages
        - total_turns: Total number of turns
    """
    result = {
        "summaries": [],
        "recent_messages": [],
        "total_turns": 0,
    }

    try:
        # Get summaries
        if include_summaries:
            summaries = await store.get_summaries(conversation_id, limit=5)
            result["summaries"] = summaries

        # Get recent messages (uncompressed sliding window)
        if include_recent:
            recent = await store.get_recent_messages(conversation_id, limit=MAX_WINDOW_SIZE)
            result["recent_messages"] = recent

        # Get total turns
        result["total_turns"] = await store.get_latest_turn(conversation_id)

    except Exception as e:
        logger.error(f"Failed to get compressed context: {e}")

    return result
