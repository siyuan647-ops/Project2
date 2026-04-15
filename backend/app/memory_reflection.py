"""Self-reflection system for meta-cognitive memory.

Periodically analyzes conversation history to generate high-level insights:
- User preferences
- Self-corrections (mistakes made)
- Interaction patterns

These become meta-memories that influence future agent behavior.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.storage import store
from app.routing.embeddings import get_embedding_service
from app.utils.prompt_boundary import wrap_historical_message

if TYPE_CHECKING:
    from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)

# Configuration
REFLECTION_INTERVAL = 10  # Trigger reflection every 10 turns
MIN_MESSAGES_FOR_REFLECTION = 5  # Minimum messages needed
CONFIDENCE_THRESHOLD = 0.6  # Minimum confidence to save a reflection


async def trigger_reflection(conversation_id: str, current_turn: int) -> list[dict]:
    """Trigger self-reflection and generate meta-memories.

    Args:
        conversation_id: The conversation ID
        current_turn: Current turn number

    Returns:
        List of generated meta-memories
    """
    try:
        # Check if we've reached reflection interval
        last_reflection = await store.get_last_reflection_turn(conversation_id)
        turns_since_reflection = current_turn - last_reflection

        if turns_since_reflection < REFLECTION_INTERVAL:
            logger.debug(
                f"Reflection not needed for {conversation_id}: "
                f"last={last_reflection}, current={current_turn}"
            )
            return []

        logger.info(
            f"Triggering reflection for {conversation_id}: "
            f"turns {last_reflection + 1} to {current_turn}"
        )

        # Get messages since last reflection
        messages = await store.get_messages_in_range(
            conversation_id,
            start_turn=last_reflection + 1,
            end_turn=current_turn
        )

        if len(messages) < MIN_MESSAGES_FOR_REFLECTION:
            logger.debug(f"Not enough messages for reflection: {len(messages)}")
            return []

        # Run all three reflection types in parallel
        reflections = await asyncio.gather(
            reflect_user_preferences(conversation_id, messages),
            reflect_self_corrections(conversation_id, messages),
            reflect_interaction_patterns(conversation_id, messages),
            return_exceptions=True
        )

        # Filter out exceptions and low-confidence results
        valid_reflections = []
        for r in reflections:
            if isinstance(r, Exception):
                logger.warning(f"Reflection failed: {r}")
                continue
            if r and r.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
                valid_reflections.append(r)

        # Save valid reflections
        saved_memories = []
        for reflection in valid_reflections:
            try:
                meta_id = await store.save_meta_memory(
                    conversation_id=conversation_id,
                    memory_type=reflection["type"],
                    content=reflection["content"],
                    evidence=reflection.get("evidence", ""),
                    confidence=reflection["confidence"],
                    turn_range=f"{last_reflection + 1}-{current_turn}",
                )

                # Generate and save embedding
                emb_service = get_embedding_service()
                embedding = emb_service.encode(reflection["content"])
                if embedding:
                    await store.update_meta_memory_embedding(meta_id, embedding)

                saved_memories.append({
                    "id": meta_id,
                    **reflection
                })

                logger.info(
                    f"Saved meta-memory for {conversation_id}: "
                    f"type={reflection['type']}, confidence={reflection['confidence']:.2f}"
                )

            except Exception as e:
                logger.error(f"Failed to save meta-memory: {e}")

        # Update last reflection turn
        await store.update_last_reflection_turn(conversation_id, current_turn)

        return saved_memories

    except Exception as e:
        logger.exception(f"Reflection failed for {conversation_id}: {e}")
        return []


async def reflect_user_preferences(conversation_id: str, messages: list[dict]) -> dict | None:
    """Analyze user messages to identify preferences and style.

    Returns a meta-memory dict or None if no clear preference detected.
    """
    from app.agents.llm_config import get_model_client
    from autogen_core.models import UserMessage

    # Filter user messages
    user_messages = [
        m for m in messages
        if m.get("event_type") == "user_message"
    ]

    if len(user_messages) < 3:
        return None

    # Build context from recent user messages with boundaries
    context = "\n\n".join([
        wrap_historical_message(m['content'][:300], "user")
        for m in user_messages[-5:]
    ])

    prompt = f"""分析以下用户提问，总结用户的偏好和风格特点：

用户提问：
{context}

请分析（如果有明确特征）：
1. 用户喜欢详细回答还是简洁回答？
2. 用户更关注哪些方面？（基本面/技术面/新闻/估值）
3. 用户的提问风格（直接/探索式/质疑式）
4. 是否有特殊要求或禁忌？

如果无法总结出明确偏好，请回答"无明显偏好"。

用一句话总结用户偏好（使用第三人称，如"用户偏好..."）："""

    try:
        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="reflection")])
        content = result.content.strip()

        # Validate result
        if "无明显偏好" in content or len(content) < 15:
            return None

        # Calculate confidence based on message variety（是否合理，后可升级为人工标注或一致性检验，或后续部署开源模型进行微调）
        confidence = min(0.9, 0.6 + len(user_messages) * 0.02)

        return {
            "type": "user_preference",
            "content": content,
            "evidence": context[:500],
            "confidence": confidence,
        }

    except Exception as e:
        logger.error(f"User preference reflection failed: {e}")
        return None


async def reflect_self_corrections(conversation_id: str, messages: list[dict]) -> dict | None:
    """Analyze conversation to identify mistakes or corrections needed.

    Returns a meta-memory dict or None if no issues detected.
    """
    from app.agents.llm_config import get_model_client
    from autogen_core.models import UserMessage

    # Build dialogue context (user + agent pairs) with boundaries
    dialogue_lines = []
    for m in messages[-10:]:  # Last 10 messages
        sender = "user" if m.get("event_type") == "user_message" else m.get("sender", "AI")
        content = m.get("content", "")[:250]
        dialogue_lines.append(wrap_historical_message(content, sender))

    dialogue = "\n\n".join(dialogue_lines)

    prompt = f"""分析以下AI与用户的对话，检查AI是否有以下问题：

对话记录：
{dialogue}

检查点：
1. AI是否给出了错误的数据或计算？
2. 用户是否纠正了AI的错误？（如"不对，PE是25不是30"）
3. AI是否误解了用户的问题？
4. AI的回答是否符合用户期望？（用户是否满意）

如果发现问题，用一句话总结教训（使用第一人称"我"，如"我需要注意..."）：
如果未发现明显问题，请回答"无明显错误"。"""

    try:
        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="reflection")])
        content = result.content.strip()

        # Validate result
        if "无明显错误" in content or len(content) < 15:
            return None

        # Higher confidence for self-corrections (usually clearer signals)
        confidence = 0.8

        return {
            "type": "self_correction",
            "content": content,
            "evidence": dialogue[:500],
            "confidence": confidence,
        }

    except Exception as e:
        logger.error(f"Self-correction reflection failed: {e}")
        return None


async def reflect_interaction_patterns(conversation_id: str, messages: list[dict]) -> dict | None:
    """Analyze interaction patterns between user and agent.

    Returns a meta-memory dict or None if no clear pattern detected.
    """
    from app.agents.llm_config import get_model_client
    from autogen_core.models import UserMessage

    # Calculate simple statistics
    user_msgs = [m for m in messages if m.get("event_type") == "user_message"]
    agent_msgs = [m for m in messages if m.get("event_type") == "agent_message"]

    if len(user_msgs) < 3:
        return None

    # Check for follow-up patterns (questions after answers)
    follow_up_count = sum(
        1 for m in user_msgs
        if "?" in m.get("content", "") or "什么" in m.get("content", "")
    )

    # Sample recent messages for context with boundaries
    recent_dialogue = "\n\n".join([
        wrap_historical_message(
            m['content'][:200],
            "user" if m.get("event_type") == "user_message" else "AI"
        )
        for m in messages[-6:]
    ])

    prompt = f"""基于以下统计和对话片段，分析用户与AI的互动模式：

统计数据：
- 用户消息数: {len(user_msgs)}
- AI回复数: {len(agent_msgs)}
- 追问/问题比例: {follow_up_count}/{len(user_msgs)}

最近对话：
{recent_dialogue}

请分析（如果有明显模式）：
1. 用户是否经常追问细节？
2. 用户是否接受AI的回答，还是经常质疑？
3. 对话是单向询问还是来回讨论？

用一句话总结互动模式（使用第三人称，如"用户倾向于..."）：
如无明显模式，请回答"无明显模式"。"""

    try:
        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="reflection")])
        content = result.content.strip()

        # Validate result
        if "无明显模式" in content or len(content) < 15:
            return None

        confidence = 0.7

        return {
            "type": "interaction_pattern",
            "content": content,
            "evidence": recent_dialogue[:400],
            "confidence": confidence,
        }

    except Exception as e:
        logger.error(f"Interaction pattern reflection failed: {e}")
        return None


async def get_active_meta_memories(conversation_id: str, min_confidence: float = 0.6) -> list[dict]:
    """Get active meta-memories for a conversation.

    Args:
        conversation_id: The conversation ID
        min_confidence: Minimum confidence threshold

    Returns:
        List of active meta-memories
    """
    try:
        all_memories = await store.get_meta_memories(conversation_id)

        # Filter by confidence and deduplicate similar memories
        filtered = [
            m for m in all_memories
            if m.get("confidence", 0) >= min_confidence
        ]

        # Sort by confidence (highest first) and take top N
        filtered.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        return filtered[:5]  # Return top 5 most confident

    except Exception as e:
        logger.error(f"Failed to get meta-memories: {e}")
        return []
