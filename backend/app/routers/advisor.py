"""Multi-agent financial advisor API routes (synchronous + multi-turn conversations)."""

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

from app.config import settings
from app.schemas.models import (
    AdvisorRequest,
    StartConversationRequest,
    FollowUpRequest,
    ConversationOut,
    ConversationDetail,
    InitialAnalysisResponse,
    FollowUpResponse,
)
from app.storage import store
from app.agents.group_chat import run_initial_analysis, run_followup
from app.memory_ingest import ingest_message, update_conversation_summary
from app.memory_compression import check_and_compress_memory
from app.memory_reflection import trigger_reflection
from app.tools.stock_data import validate_ticker
from app.context import set_conversation_id

router = APIRouter()
limiter = Limiter(key_func=get_remote_address, config_filename=None)

_TICKER_RE = re.compile(r"^[A-Z0-9.]{1,10}$")


# ── Conversation lifecycle ──────────────────────────────────────────

#创建新会话
@router.post("/conversations", response_model=ConversationOut)
@limiter.limit(settings.RATE_LIMIT_ADVISOR)
async def start_conversation(request: Request, req: StartConversationRequest):
    """Create a new conversation and return its metadata (no analysis yet)."""
    ticker = req.ticker.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format. Expected 1-10 uppercase letters/numbers.")

    # 验证股票代码是否存在
    is_valid, error_msg = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg or f"Stock ticker '{ticker}' not found.")

    conv = await store.create_conversation(ticker)
    return conv    #返回对话元数据（ID、ticker等）


#列出最近对话
@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(limit: int = 20):
    """List recent conversations."""
    return await store.list_conversations(limit=min(limit, 100))

#查询单个对话详情
@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: str):
    """Get conversation metadata + all messages."""
    conv = await store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = await store.get_messages(conv_id)
    return {**conv, "messages": messages}


# ── Synchronous analysis endpoints ─────────────────────────────────

#首轮分析
@router.post("/conversations/{conv_id}/initial", response_model=InitialAnalysisResponse)
@limiter.limit(settings.RATE_LIMIT_ADVISOR)
async def initial_analysis(request: Request, conv_id: str):
    """
    Run the full three-agent analysis as turn 1 of a conversation.
    Returns the complete report synchronously.
    """
    conv = await store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    ticker = conv["ticker"]
    turn = await store.get_latest_turn(conv_id) + 1

    # Set conversation context for tool call logging
    set_conversation_id(conv_id)

    # Run analysis synchronously
    report = await run_initial_analysis(ticker, conversation_id=conv_id)

    # Save the report message
    msg = await store.add_message(conv_id, turn, "Investment_Advisor", report, "agent_message")
    await ingest_message(conv_id, msg["id"], turn, "Investment_Advisor", report, "agent_message")
    await update_conversation_summary(conv_id)

    return {
        "conversation_id": conv_id,
        "turn": turn,
        "ticker": ticker,
        "report": report,
    }



#追问（第二轮及后续）：
#1. 压缩记忆（滚动摘要）
#2. 自我反思（元记忆）
#3. 分析决策（路由）
#4. 回答问题（投资顾问）
#5. 保存消息（存储）
@router.post("/conversations/{conv_id}/messages", response_model=FollowUpResponse)
@limiter.limit(settings.RATE_LIMIT_ADVISOR)
async def followup(request: Request, conv_id: str, req: FollowUpRequest):
    """
    Send a follow-up question in an existing conversation.
    Returns the answer synchronously; Investment_Advisor answers by default,
    escalating to other agents when needed.
    """
    conv = await store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    ticker = conv["ticker"]
    turn = await store.get_latest_turn(conv_id) + 1

    # Persist the user's question
    user_msg = await store.add_message(conv_id, turn, "user", req.question, "user_message")
    await ingest_message(conv_id, user_msg["id"], turn, "user", req.question, "user_message")

    # Trigger memory compression if needed (async fire-and-forget)
    try:
        was_compressed = await check_and_compress_memory(conv_id)
        if was_compressed:
            logger.info(f"Memory compressed for conversation {conv_id}")
    except Exception as e:
        logger.warning(f"Memory compression failed for {conv_id}: {e}")

    # Trigger self-reflection if needed
    try:
        reflections = await trigger_reflection(conv_id, turn)
        if reflections:
            logger.info(f"Generated {len(reflections)} meta-memories for {conv_id}")
    except Exception as e:
        logger.warning(f"Self-reflection failed for {conv_id}: {e}")

    # Set conversation context for tool call logging
    set_conversation_id(conv_id)

    # Run analysis synchronously
    answer, routing_decision = await run_followup(
        ticker=ticker,
        question=req.question,
        conversation_id=conv_id,
    )

    # Save the answer message
    msg = await store.add_message(conv_id, turn, "Investment_Advisor", answer, "agent_message")
    await ingest_message(conv_id, msg["id"], turn, "Investment_Advisor", answer, "agent_message")
    await update_conversation_summary(conv_id)

    return {
        "conversation_id": conv_id,
        "turn": turn,
        "ticker": ticker,
        "answer": answer,
        "routing": {
            "route": routing_decision.route,
            "confidence": round(routing_decision.confidence, 3),
            "source": routing_decision.source,
            "rationale": routing_decision.rationale,
            "requires_fresh_data": routing_decision.requires_fresh_data,
        },
    }


# ── Legacy one-shot endpoint (backward compatibility) ───────────────

@router.post("/analyze")
@limiter.limit(settings.RATE_LIMIT_ADVISOR)
async def analyze_stock(request: Request, req: AdvisorRequest):
    """
    Legacy one-shot analysis. Creates a temporary conversation under
    the hood so it also gets persisted.
    """
    ticker = req.ticker.upper().strip()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format. Expected 1-10 uppercase letters/numbers.")

    # 验证股票代码是否存在
    is_valid, error_msg = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg or f"Stock ticker '{ticker}' not found.")

    conv = await store.create_conversation(ticker)
    conv_id = conv["id"]
    turn = 1

    # Set conversation context for tool call logging
    set_conversation_id(conv_id)

    # Run analysis synchronously
    report = await run_initial_analysis(ticker, conversation_id=conv_id)

    msg = await store.add_message(conv_id, turn, "Investment_Advisor", report, "agent_message")
    await ingest_message(conv_id, msg["id"], turn, "Investment_Advisor", report, "agent_message")
    await update_conversation_summary(conv_id)

    return {
        "ticker": ticker,
        "report": report,
    }


# ── Agent traces endpoints (for debugging and transparency) ─────────

@router.get("/conversations/{conv_id}/traces")
async def get_conversation_traces(
    conv_id: str,
    trace_type: str | None = None,
    limit: int = 100,
):
    """Get agent traces for a conversation to see the thinking process."""
    conv = await store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    traces = await store.get_agent_traces(conv_id, trace_type=trace_type, limit=limit)
    return {
        "conversation_id": conv_id,
        "count": len(traces),
        "traces": traces,
    }


@router.get("/conversations/{conv_id}/traces/summary")
async def get_conversation_trace_summary(conv_id: str):
    """Get a summary of agent traces for a conversation."""
    conv = await store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    summary = await store.get_agent_trace_summary(conv_id)
    return summary
