"""GroupChat orchestration – runs the multi-agent advisory workflow.

Provides two entry points:
- run_initial_analysis_stream: full three-agent team analysis (turn 1).
- run_followup_stream: follow-up question; Investment Advisor answers by
  default, escalating to Research / Financial agents when necessary.
  Uses the hybrid routing pipeline (embedding → rules → LLM) to decide.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, cast
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage, ToolCallSummaryMessage
from autogen_agentchat.teams import SelectorGroupChat

from app.agents.llm_config import get_model_client
from app.agents.investment_advisor import create_investment_advisor
from app.agents.parallel_analysis import run_parallel_analysis
from app.agents.react_analyst import create_react_analyst
from app.routing import route_followup as _route_followup, RoutingDecision
from app.routing.embeddings import get_embedding_service
from app.storage import store
from app.memory_reflection import get_active_meta_memories
from app.utils.prompt_boundary import wrap_user_input

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

"""提取消息内容"""
def _routing_decision_trace_dict(decision: RoutingDecision) -> dict[str, Any]:
    return {
        "route": decision.route,
        "confidence": decision.confidence,
        "rationale": decision.rationale,
        "source": decision.source,
        "requires_fresh_data": decision.requires_fresh_data,
        "metadata": decision.metadata or {},
    }


def _serialize_trace_messages(messages: list[Any], *, max_content_chars: int = 12000) -> list[dict[str, Any]]:
    """Flatten AutoGen messages for eval / audit (truncated)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        src = getattr(m, "source", None)
        typ = type(m).__name__
        content = _extract_content(m)
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n... [truncated]"
        row: dict[str, Any] = {"source": src, "type": typ, "content": content}
        mu = getattr(m, "models_usage", None)
        if mu is not None:
            row["usage"] = {
                "prompt_tokens": getattr(mu, "prompt_tokens", 0),
                "completion_tokens": getattr(mu, "completion_tokens", 0),
            }
        out.append(row)
    return out


def _extract_content(message: Any) -> str:
    if isinstance(message, (TextMessage, ToolCallSummaryMessage)):
        return message.content
    if hasattr(message, "content") and isinstance(message.content, str):
        return message.content
    return ""


"""得到最近8轮对话"""
def _build_history_summary(history: list[dict], max_chars: int = 6000) -> str:
    """Condense stored messages into a compact text block for context injection."""
    if not history:
        return ""
    lines: list[str] = []
    total = 0
    # Walk backwards so recent messages are always included
    for msg in reversed(history):
        if msg.get("event_type") == "user_message":
            line = f"[User] {msg['content']}"
        else:
            line = f"[{msg['sender']}] {msg['content']}"
        if total + len(line) > max_chars:
            lines.append("... (earlier messages omitted) ...")
            break
        lines.append(line)
        total += len(line)
    lines.reverse()
    return "\n\n".join(lines)


"""构建上下文"""
async def _build_context(
    conversation_id: str,
    question: str,
    *,
    recent_limit: int = 8,
    chunk_limit: int = 5,
) -> str:
    """Build enhanced context with sliding window, summaries, and meta-memories.

    Layer 0 – Meta-memories (user preferences, self-corrections, patterns)
    Layer 1 – Compressed summaries (older history)
    Layer 2 – Recent messages (sliding window, last 8 turns)
    Layer 3 – Semantically relevant memory chunks (RAG)
    Layer 4 – Tool call logs (raw data sources)

    All layers annotated with【数据来源】for strict source tracking.
    """
    parts: list[str] = []

    # Layer 0: Meta-memories (highest priority - user preferences, etc.)
    try:
        meta_memories = await get_active_meta_memories(conversation_id, min_confidence=0.6)
        if meta_memories:
            meta_parts = []
            for mm in meta_memories:
                memory_type = mm.get('memory_type', '')
                content = mm.get('content', '')
                confidence = mm.get('confidence', 0.7)

                if memory_type == 'user_preference':
                    meta_parts.append(f"【用户偏好 | 置信度{confidence:.0%}】{content}")
                elif memory_type == 'self_correction':
                    meta_parts.append(f"【自我修正 | 置信度{confidence:.0%}】{content}")
                elif memory_type == 'interaction_pattern':
                    meta_parts.append(f"【互动模式 | 置信度{confidence:.0%}】{content}")

            if meta_parts:
                parts.append("## 高阶认知（Agent自省）\n" + "\n".join(meta_parts))
    except Exception as e:
        logger.warning(f"Failed to load meta-memories: {e}")

    # Layer 1: Compressed summaries (older history)
    try:
        emb_service = get_embedding_service()
        query_vec = emb_service.encode(question)

        if query_vec is not None:
            summaries = await store.search_summaries(conversation_id, query_vec, limit=2)
            if summaries:
                summary_parts = []
                for s in summaries:
                    turn_range = s.get('turn_range', '')
                    summary_parts.append(
                        f"【历史摘要 | 轮次{turn_range}】{s['content'][:400]}"
                    )
                parts.append("## 历史对话摘要\n" + "\n".join(summary_parts))
    except Exception as e:
        logger.warning(f"Failed to load summaries: {e}")

    # Layer 2: Recent messages (sliding window)
    try:
        recent = await store.get_recent_messages(conversation_id, limit=recent_limit)
        if recent:
            recent_text = _build_history_summary(recent)
            parts.append(f"【数据来源：近期对话（最近{len(recent)}轮）】\n{recent_text}")
    except Exception as e:
        logger.warning(f"Failed to load recent messages: {e}")

    # Layer 3: Semantic retrieval (RAG)
    try:
        if query_vec is not None:
            chunks = await store.search_similar_chunks(
                conversation_id, query_vec, limit=chunk_limit,
            )
            if chunks:
                chunk_parts = []
                for c in chunks:
                    chunk_parts.append(f"【数据来源：历史记忆 | 类型：{c['chunk_type']}】\n{c['content']}")
                parts.append("\n".join(chunk_parts))
    except Exception as e:
        logger.warning(f"Failed to search chunks: {e}")

    # Layer 4: Tool call logs (raw data sources)
    try:
        tool_logs = await store.get_recent_tool_logs(conversation_id, limit=5)
        if tool_logs:
            tool_parts = []
            for log in tool_logs:
                tool_parts.append(
                    f"【数据来源：{log['data_source']} | 工具：{log['tool_name']}】\n"
                    f"{log['result_summary']}"
                )
            parts.append("\n\n".join(tool_parts))
    except Exception as e:
        logger.warning(f"Failed to load tool logs: {e}")

    return "\n\n".join(parts) if parts else ""


# ── Initial full analysis (turn 1) ──────────────────────────────────

async def run_initial_analysis(
    ticker: str,
    conversation_id: str | None = None,
) -> str:
    """Launch the full three-agent analysis for *ticker* and return complete report.

    Uses parallel execution: Research and Financial analysts run concurrently,
    then Investment Advisor synthesizes both results.
    """
    # 【优化】: 使用并行分析，Research 和 Financial 同时执行
    return await run_parallel_analysis(ticker, conversation_id=conversation_id)


# ── Follow-up (turn 2+) ─────────────────────────────────────────────

async def run_followup(
    ticker: str,
    question: str,
    conversation_id: str,
    *,
    collect_trace: bool = False,
) -> tuple[str, RoutingDecision] | tuple[str, RoutingDecision, dict[str, Any]]:
    """
    Handle a follow-up question within an existing conversation.

    Returns (answer, routing_decision), or (answer, routing_decision, trace) when
    collect_trace=True. Trace includes routing summary, timing, context size, and
    serialized agent messages (CoT / tool summaries when present).
    """
    import time

    followup_start = time.time()
    store_local = store  # Capture for error logging

    try:
        # 1. 构建上下文
        context_start = time.time()
        context_text = await _build_context(conversation_id, question)
        context_duration = int((time.time() - context_start) * 1000)
        await store_local.log_performance_metric(
            metric_type="context_build",
            component="group_chat",
            duration_ms=context_duration,
            conversation_id=conversation_id,
            metadata={"ticker": ticker, "question_length": len(question)}
        )

        # 2. 路由决策
        routing_start = time.time()
        decision = await _route_followup(
            ticker=ticker,
            question=question,
            history_summary=context_text,
        )
        routing_duration = int((time.time() - routing_start) * 1000)
        await store_local.log_performance_metric(
            metric_type="routing",
            component="enhanced_router",
            duration_ms=routing_duration,
            conversation_id=conversation_id,
            metadata={
                "route": decision.route,
                "confidence": decision.confidence,
                "source": decision.source,
                "intent_category": decision.metadata.get("intent_category") if decision.metadata else None,
            }
        )

        logger.info(
            "Routing decision for '%s': route=%s confidence=%.2f source=%s rationale=%s",
            question[:60], decision.route, decision.confidence,
            decision.source, decision.rationale,
        )

        mode = decision.route

        # 3. 执行回答
        execution_start = time.time()
        agent_messages_trace: list[dict[str, Any]] = []

        if mode == "unknown":
            rejection = (
                "抱歉，我是一个专注于股票投资分析的助手，无法回答与股票分析无关的问题。"
                "请您提出与股票研究、财务分析或投资建议相关的问题，我会尽力为您服务。"
            )
            execution_duration = int((time.time() - execution_start) * 1000)
            total_duration = int((time.time() - followup_start) * 1000)
            if collect_trace:
                trace = {
                    "routing": _routing_decision_trace_dict(decision),
                    "context_chars": len(context_text),
                    "timings_ms": {
                        "context_build": context_duration,
                        "routing": routing_duration,
                        "execution": execution_duration,
                        "total_followup": total_duration,
                    },
                    "agent_messages": agent_messages_trace,
                    "token_totals": _aggregate_trace_usage(agent_messages_trace),
                }
                return rejection, decision, trace
            return rejection, decision

        if mode == "advisor_only":
            if collect_trace:
                answer, agent_messages_trace = cast(
                    tuple[str, list[dict[str, Any]]],
                    await _run_advisor_only_sync(
                        ticker, question, context_text, collect_trace=True,
                    ),
                )
            else:
                answer = await _run_advisor_only_sync(ticker, question, context_text)
        else:
            # All other routes (research, financial, full) use ReAct agent
            # 提取意图主类别，指导ReAct工具选择
            intent_category = decision.metadata.get("intent_category") if decision.metadata else None

            if collect_trace:
                answer, agent_messages_trace = cast(
                    tuple[str, list[dict[str, Any]]],
                    await _run_react_followup(
                        ticker, question, context_text,
                        intent_category=intent_category,
                        conversation_id=conversation_id,
                        collect_trace=True,
                    ),
                )
            else:
                answer = await _run_react_followup(
                    ticker, question, context_text,
                    intent_category=intent_category,
                    conversation_id=conversation_id,
                )

        execution_duration = int((time.time() - execution_start) * 1000)
        await store_local.log_performance_metric(
            metric_type="agent_execution",
            component="react_followup" if mode != "advisor_only" else "advisor_only",
            duration_ms=execution_duration,
            conversation_id=conversation_id,
            metadata={"route": mode, "answer_length": len(answer)}
        )

        # 4. 总耗时
        total_duration = int((time.time() - followup_start) * 1000)
        await store_local.log_performance_metric(
            metric_type="total",
            component="followup_pipeline",
            duration_ms=total_duration,
            conversation_id=conversation_id,
            metadata={"route": mode}
        )

        if collect_trace:
            trace = {
                "routing": _routing_decision_trace_dict(decision),
                "context_chars": len(context_text),
                "timings_ms": {
                    "context_build": context_duration,
                    "routing": routing_duration,
                    "execution": execution_duration,
                    "total_followup": total_duration,
                },
                "agent_messages": agent_messages_trace,
                "token_totals": _aggregate_trace_usage(agent_messages_trace),
            }
            return answer, decision, trace
        return answer, decision

    except Exception as e:
        # 记录错误
        total_duration = int((time.time() - followup_start) * 1000)
        await store_local.log_error(
            error_type="followup_error",
            component="group_chat.run_followup",
            error_message=str(e),
            conversation_id=conversation_id,
            severity="critical",
            metadata={
                "ticker": ticker,
                "question": question[:200],
                "total_duration_ms": total_duration,
            }
        )
        raise


def _aggregate_trace_usage(agent_messages: list[dict[str, Any]]) -> dict[str, int]:
    pt, ct = 0, 0
    for m in agent_messages:
        u = m.get("usage") or {}
        pt += int(u.get("prompt_tokens") or 0)
        ct += int(u.get("completion_tokens") or 0)
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
    }


async def _run_advisor_only_sync(
    ticker: str, question: str, context_text: str,
    *,
    collect_trace: bool = False,
) -> str | tuple[str, list[dict[str, Any]]]:
    """Investment Advisor answers a follow-up using only conversation history."""
    advisor = create_investment_advisor()
    wrapped_question = wrap_user_input(question)

    task = (
        f"You are analyzing **{ticker}** based on the provided context.\n\n"
        f"## CONTEXT (带【数据来源】标记的事实数据可直接使用):\n{context_text}\n\n"
        f"## User Question\n{wrapped_question}\n\n"
        "## INSTRUCTIONS\n"
        "1. 【数据来源】标记的事实数据（股价、PE、营收等）必须使用，不得编造\n"
        "2. 投资分析方法、行业趋势判断等可使用你的专业知识\n"
        "3. 如无具体数据支撑，明确说明'该信息未在提供的资料中找到'\n"
        "4. 提供详细回答（至少300字），使用专业中文\n"
        "5. End with \"FOLLOW-UP RESPONSE COMPLETE\""
    )

    response = await advisor.run(task=task)
    content = _extract_content(response.messages[-1]) if response.messages else ""
    if collect_trace:
        return content, _serialize_trace_messages(list(response.messages))
    return content


def _get_intent_tool_guide(intent_category: str | None) -> str:
    """根据意图主类别返回工具选择建议"""
    guides = {
        "financial_metrics": (
            "【工具选择建议】\n"
            "- 优先调用: get_stock_info (获取PE、市值等), get_financial_statements (获取ROE、EPS等)\n"
            "- 重点获取: 具体财务指标数值及历史趋势\n"
            "- 无需调用新闻类工具"
        ),
        "financial_risk": (
            "【工具选择建议】\n"
            "- 优先调用: get_financial_statements (分析负债、现金流)\n"
            "- 重点分析: 债务水平、现金流动性、应收账款风险\n"
            "- 关注: 流动比率、速动比率、负债率变化"
        ),
        "research": (
            "【工具选择建议】\n"
            "- 优先调用: search_company_news (获取最新新闻)\n"
            "- 次要调用: get_stock_info (补充行业对比数据)\n"
            "- 重点获取: 近期催化剂、竞争动态、行业趋势"
        ),
        "advisor": (
            "【工具选择建议】\n"
            "- **无需调用任何工具**\n"
            "- 基于已有上下文和专业知识直接回答\n"
            "- 如需补充数据再考虑调用工具"
        ),
        "ambiguous": (
            "【工具选择建议】\n"
            "- 先调用 get_stock_info 获取基础信息\n"
            "- 根据初步结果决定是否需要进一步调用其他工具\n"
            "- 保持灵活，观察用户需求"
        ),
        "off_topic": (
            "【处理方式】\n"
            "- 直接拒绝，说明只能回答股票分析相关问题\n"
            "- 建议用户提出与股票研究、财务分析或投资建议相关的问题"
        ),
    }
    return guides.get(intent_category, "")


def _select_speaker(messages: list[Any]) -> str | None:
    """选择发言者：ReAct完成分析后，才让Advisor发言。

    保护机制：
    - ReAct发言超过8轮强制让Advisor介入兜底
    """
    if not messages:
        return "ReAct_Analyst"

    last_message = messages[-1]
    content = _extract_content(last_message) or ""

    # 如果ReAct明确说分析完成，让Advisor综合回答
    if "ANALYSIS COMPLETE" in content:
        return "Investment_Advisor"

    # 保护机制：ReAct发言超过8轮，强制让Advisor介入
    react_count = sum(
        1 for m in messages
        if hasattr(m, 'source') and m.source == "ReAct_Analyst"
    )
    if react_count >= 8:
        logger.warning(f"ReAct has spoken {react_count} times, forcing Advisor to take over")
        return "Investment_Advisor"

    # 正常流程：继续让ReAct分析
    return "ReAct_Analyst"


async def _run_react_followup(
    ticker: str,
    question: str,
    context_text: str,
    intent_category: str | None = None,
    conversation_id: str | None = None,
    *,
    collect_trace: bool = False,
) -> str | tuple[str, list[dict[str, Any]]]:
    """Run a follow-up using ReAct agent that dynamically decides tool calls.

    The ReAct agent will:
    1. Analyze the question and determine what information is needed
    2. Call appropriate tools in sequence based on reasoning
    3. Iterate until sufficient information is gathered
    4. Synthesize findings into a comprehensive answer
    """
    import time

    react_start = time.time()
    store_local = store

    try:
        # Create ReAct analyst with all tools
        react_analyst = create_react_analyst()

        # Create investment advisor for final synthesis
        advisor = create_investment_advisor()

        termination = (
            TextMentionTermination(
                "FOLLOW-UP RESPONSE COMPLETE",
                sources=["Investment_Advisor"],
            )
            | MaxMessageTermination(20)
        )

        # Use SelectorGroupChat: 智能选择发言者
        team = SelectorGroupChat(
            participants=[react_analyst, advisor],
            model_client=get_model_client(),
            selector_func=_select_speaker,
            termination_condition=termination,
        )

        wrapped_question = wrap_user_input(question)

        # 获取意图对应的工具指导
        intent_guide = _get_intent_tool_guide(intent_category)
        intent_section = f"\n## Intent Classification\n用户意图类别: {intent_category or 'unknown'}\n{intent_guide}\n\n" if intent_category else ""

        task = (
        f"## Prior conversation context about {ticker}\n{context_text}\n\n"
        f"## User's follow-up question\n{wrapped_question}\n"
        f"{intent_section}"
        "## Task Instructions\n"
        "1. ReAct_Analyst: Analyze the user's question and dynamically call tools to gather information. "
        "   - Use Thought → Action → Observation pattern\n"
        "   - 参考上述【工具选择建议】优先调用相关工具\n"
        "   - Only call tools that are necessary for this specific question\n"
        "   - When you have enough information, provide your analysis and end with 'ANALYSIS COMPLETE'\n\n"
        "2. Investment_Advisor: Review the analysis and provide a final, comprehensive answer.\n"
        "   - If ReAct_Analyst has completed analysis: Synthesize findings into clear investment insights\n"
        "   - If ReAct_Analyst was interrupted or couldn't complete: Based on available context and conversation history, provide the best possible answer or explain what information is missing\n"
        "   - Use professional Chinese (at least 300 words)\n"
        "   - Add the standard disclaimer\n"
        '   - End with "FOLLOW-UP RESPONSE COMPLETE"'
    )

        result = await team.run(task=task)

        # 记录执行统计
        react_duration = int((time.time() - react_start) * 1000)
        message_count = len(result.messages)
        react_messages = sum(1 for m in result.messages if hasattr(m, 'source') and m.source == "ReAct_Analyst")

        await store_local.log_performance_metric(
            metric_type="agent_execution",
            component="react_team",
            duration_ms=react_duration,
            conversation_id=conversation_id,
            metadata={
                "message_count": message_count,
                "react_messages": react_messages,
                "intent_category": intent_category,
            }
        )

        # Extract the final content from Investment_Advisor
        answer = "分析完成，但未生成答案。"
        for message in reversed(result.messages):
            content = _extract_content(message)
            if content and message.source == "Investment_Advisor":
                answer = content
                break
        else:
            if result.messages:
                answer = _extract_content(result.messages[-1])

        if collect_trace:
            return answer, _serialize_trace_messages(list(result.messages))
        return answer

    except Exception as e:
        # 记录 ReAct 执行错误
        react_duration = int((time.time() - react_start) * 1000)
        await store_local.log_error(
            error_type="react_execution_error",
            component="group_chat._run_react_followup",
            error_message=str(e),
            conversation_id=conversation_id,
            severity="critical",
            metadata={
                "ticker": ticker,
                "question": question[:200],
                "intent_category": intent_category,
                "duration_ms": react_duration,
            }
        )
        raise
