"""Memory chunk ingestion pipeline.

Converts persisted messages into vectorised memory chunks that power
semantic retrieval in _build_context() Layer 3.

Design:
- 1 message = 1 chunk (MVP strategy, simple and predictable).
- Embedding failures are tolerated: chunks are still stored with
  embedding=NULL so they can be back-filled later.
- Importance is derived from sender role (advisor > analyst > user).
- Trivial / boilerplate content is filtered out (Phase B quality).
- Idempotent: skips if a chunk for (conversation_id, message_id, chunk_type)
  already exists.
"""

from __future__ import annotations

import logging
import re

from app.routing.embeddings import get_embedding_service
from app.storage import store

logger = logging.getLogger(__name__)

# ── Chunk-type mapping ───────────────────────────────────────────────

_CHUNK_TYPE_MAP: dict[str, str] = {
    "user_message": "user_question",
    "agent_message": "agent_answer",
}

_SENDER_IMPORTANCE: dict[str, float] = {
    "user": 0.4,
    "Investment_Advisor": 0.8,
    "Financial_Analyst": 0.7,
    "Research_Analyst": 0.7,
}

# ── Phase B: content filters ────────────────────────────────────────

_MIN_CONTENT_LENGTH = 8
_MAX_CONTENT_LENGTH = 4000  # truncate very long agent outputs

_TRIVIAL_PATTERNS = [
    re.compile(r"^(FOLLOW-UP RESPONSE COMPLETE|INVESTMENT ADVISORY REPORT COMPLETE)\s*$", re.I),
    re.compile(r"^\s*$"),
]


def _is_trivial(content: str) -> bool:
    """Return True if content is too short or matches boilerplate."""
    if len(content.strip()) < _MIN_CONTENT_LENGTH:
        return True
    for pat in _TRIVIAL_PATTERNS:
        if pat.match(content.strip()):
            return True
    return False

#截断（避免单条过长占库和耗时）
def _truncate(content: str) -> str:
    if len(content) <= _MAX_CONTENT_LENGTH:
        return content
    return content[:_MAX_CONTENT_LENGTH] + "…"


def _resolve_chunk_type(sender: str, event_type: str) -> str:
    """Derive a chunk_type label from sender and event_type."""
    if event_type == "user_message":
        return "user_question"
    # Agent messages: use sender-based labels
    sender_lower = sender.lower()
    if "research" in sender_lower:
        return "research_note"
    if "financial" in sender_lower:
        return "financial_note"
    if "advisor" in sender_lower or "investment" in sender_lower:
        return "advisor_answer"
    return _CHUNK_TYPE_MAP.get(event_type, "agent_answer")


# ── Core ingestion function ─────────────────────────────────────────

async def ingest_message(
    conversation_id: str,
    message_id: str,
    turn: int,
    sender: str,
    content: str,
    event_type: str = "agent_message",
) -> None:
    """Ingest a single message into memory_chunks (idempotent).

    This is the main entry point called from advisor.py after each
    store.add_message().  It is intentionally fire-and-forget safe:
    failures are logged but never propagated to the caller.
    """
    try:
        # Phase B: skip trivial content
        if _is_trivial(content):
            return

        chunk_type = _resolve_chunk_type(sender, event_type)

        # Phase A3: idempotency check
        existing = await store.chunk_exists(conversation_id, message_id, chunk_type)
        if existing:
            return

        # Truncate very long content
        chunk_content = _truncate(content)

        # Generate embedding (tolerant of failure)
        emb_service = get_embedding_service()
        embedding = emb_service.encode(chunk_content)
        if embedding is None:
            logger.warning(
                "Embedding unavailable for msg %s; storing chunk without vector.",
                message_id,
            )

        importance = _SENDER_IMPORTANCE.get(sender, 0.5)

        await store.add_memory_chunk(
            conversation_id=conversation_id,
            content=chunk_content,
            chunk_type=chunk_type,
            embedding=embedding,
            message_id=message_id,
            importance=importance,
            turn=turn,
        )

        # Also back-fill messages.embedding for parity
        if embedding is not None:
            await store.update_message_embedding(message_id, embedding)

    except Exception:
        logger.exception("Memory ingest failed for message %s – skipping.", message_id)


# ── Phase B2: summary maintenance（写进 DB 并通过会话 API 给前端/运维看） ───────────────────────────────────

_SUMMARY_MAX_CHARS = 1500


async def update_conversation_summary(
    conversation_id: str,
) -> None:
    """Rebuild a compact rolling summary from the latest messages.

    Called after each completed turn.  Uses a simple heuristic:
    concatenate the most recent user questions and advisor answers
    into a brief digest.  A future version could use an LLM to
    generate a true abstractive summary.
    """
    try:
        recent = await store.get_recent_messages(conversation_id, limit=10)
        if not recent:
            return

        lines: list[str] = []
        total = 0
        for msg in recent:
            if msg.get("event_type") == "user_message":
                line = f"Q: {msg['content'][:300]}"
            elif msg.get("sender", "").lower() in (
                "investment_advisor", "financial_analyst", "research_analyst",
            ):
                line = f"{msg['sender']}: {msg['content'][:300]}"
            else:
                continue
            if total + len(line) > _SUMMARY_MAX_CHARS:
                break
            lines.append(line)
            total += len(line)

        summary_text = "\n".join(lines)
        await store.update_conversation(conversation_id, summary=summary_text)

    except Exception:
        logger.exception(
            "Summary update failed for conversation %s – skipping.",
            conversation_id,
        )


# ── Phase C2: batch backfill ────────────────────────────────────────

async def backfill_conversation(conversation_id: str) -> int:
    """Back-fill memory chunks for all existing messages in a conversation.

    Returns the number of newly created chunks.  Idempotent.
    """
    messages = await store.get_messages(conversation_id)
    created = 0
    for msg in messages:
        chunk_type = _resolve_chunk_type(msg["sender"], msg["event_type"])
        existing = await store.chunk_exists(
            conversation_id, msg["id"], chunk_type,
        )
        if existing:
            continue
        if _is_trivial(msg["content"]):
            continue

        chunk_content = _truncate(msg["content"])
        emb_service = get_embedding_service()
        embedding = emb_service.encode(chunk_content)
        importance = _SENDER_IMPORTANCE.get(msg["sender"], 0.5)

        await store.add_memory_chunk(
            conversation_id=conversation_id,
            content=chunk_content,
            chunk_type=chunk_type,
            embedding=embedding,
            message_id=msg["id"],
            importance=importance,
            turn=msg["turn"],
        )
        created += 1
    return created


async def backfill_all(limit: int = 100) -> dict[str, int]:
    """Back-fill all conversations.  Returns {conv_id: chunks_created}."""
    conversations = await store.list_conversations(limit=limit)
    results: dict[str, int] = {}
    for conv in conversations:
        n = await backfill_conversation(conv["id"])
        if n > 0:
            results[conv["id"]] = n
    return results
