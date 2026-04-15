"""增强版路由管线 - 集成RAG意图识别能力

在原有三级管线（embedding → rules → LLM）基础上，增加RAG意图召回层，
通过Few-shot学习提升垂类意图识别的准确性。

Pipeline:
    embedding → rules → RAG检索 → Few-shot LLM → decision
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any

from app.routing.types import Route, RoutingDecision, EmbeddingSignal, RuleSignal
from app.routing.embeddings import get_embedding_service
from app.routing.rules import evaluate_rules
from app.routing.rag_intent_retriever import (
    get_rag_retriever,
    IntentCase,
    retrieve_intent_cases,
    RAGIntentRetriever,
)
from app.routing.intent_prompt_builder import (
    build_few_shot_intent_prompt,
    parse_intent_response,
)
from app.config import settings
from app.utils.prompt_boundary import wrap_user_input

logger = logging.getLogger(__name__)

# 配置参数
_RULE_CONFIDENCE_THRESHOLD = 0.7  # 规则引擎高置信度阈值
_RAG_HIGH_CONFIDENCE_THRESHOLD = 0.75  # RAG高置信度阈值
_RAG_LOW_CONFIDENCE_THRESHOLD = 0.5  # RAG低置信度阈值


async def enhanced_route_followup(
    ticker: str,
    question: str,
    history_summary: str = "",
    enable_rag: bool = True,
    enable_few_shot: bool = True,
    # 可配置阈值参数（用于阈值调优）
    rule_confidence_threshold: float | None = None,
    rag_high_confidence_threshold: float | None = None,
    rag_low_confidence_threshold: float | None = None,
) -> RoutingDecision:
    """增强版路由管线 - 集成RAG意图识别

    Args:
        ticker: 股票代码
        question: 用户问题
        history_summary: 对话历史摘要
        enable_rag: 是否启用RAG召回
        enable_few_shot: 是否启用Few-shot LLM
        rule_confidence_threshold: 规则引擎阈值（默认0.7）
        rag_high_confidence_threshold: RAG高置信度阈值（默认0.75）
        rag_low_confidence_threshold: RAG低置信度阈值（默认0.5）

    Returns:
        路由决策
    """
    # 使用传入的阈值或默认值
    rule_threshold = rule_confidence_threshold if rule_confidence_threshold is not None else _RULE_CONFIDENCE_THRESHOLD
    rag_high_threshold = rag_high_confidence_threshold if rag_high_confidence_threshold is not None else _RAG_HIGH_CONFIDENCE_THRESHOLD
    rag_low_threshold = rag_low_confidence_threshold if rag_low_confidence_threshold is not None else _RAG_LOW_CONFIDENCE_THRESHOLD
    """增强版路由管线 - 集成RAG意图识别

    Args:
        ticker: 股票代码
        question: 用户问题
        history_summary: 对话历史摘要
        enable_rag: 是否启用RAG召回
        enable_few_shot: 是否启用Few-shot LLM

    Returns:
        路由决策
    """

    # ========== Stage 1: Embedding 粗筛 ==========
    emb_service = get_embedding_service()
    emb_signal = emb_service.compute_signal(query=question, ticker=ticker)

    # ========== Stage 2: 规则引擎 ==========
    rule_signal = evaluate_rules(question)

    # 硬规则直接返回（最高优先级）
    if rule_signal.hard_route is not None:
        return RoutingDecision(
            route=rule_signal.hard_route,
            confidence=1.0,
            rationale=f"硬规则匹配: {rule_signal.matched_rules}",
            source="hard_rule",
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
            requires_fresh_data=rule_signal.hard_route in ("research", "financial", "full"),
            metadata={"stage": "hard_rule"}
        )

    # 软规则高置信度直接返回
    if rule_signal.soft_scores:
        best_route = max(rule_signal.soft_scores, key=rule_signal.soft_scores.get)
        best_score = rule_signal.soft_scores[best_route]
        if best_score >= rule_threshold:
            return RoutingDecision(
                route=best_route,
                confidence=best_score,
                rationale=f"软规则高置信度: {rule_signal.matched_rules}",
                source="soft_rule",
                embedding_signal=emb_signal,
                rule_signal=rule_signal,
                requires_fresh_data=best_route in ("research", "financial", "full"),
                metadata={"stage": "soft_rule", "score": best_score}
            )

    # ========== Stage 3: RAG意图召回 ==========
    retrieved_cases: list[IntentCase] = []
    high_confidence_route: Optional[str] = None

    if enable_rag:
        try:
            retriever = get_rag_retriever()
            retrieved_cases = await retriever.retrieve_similar_intents(
                query=question,
                top_k=5,
                similarity_threshold=rag_low_threshold,
                diversify=True
            )

            # 检查是否有极高置信度的匹配（可跳过LLM）
            high_confidence_route = retriever.get_high_confidence_route(
                retrieved_cases,
                threshold=rag_high_threshold
            )

            if high_confidence_route and not enable_few_shot:
                # RAG直接决策（快速路径）
                top_case = retrieved_cases[0]
                return RoutingDecision(
                    route=high_confidence_route,
                    confidence=top_case.similarity,
                    rationale=f"RAG高置信度匹配: {top_case.intent_category}/{top_case.intent_subcategory}",
                    source="rag_direct",
                    embedding_signal=emb_signal,
                    rule_signal=rule_signal,
                    requires_fresh_data=high_confidence_route in ("research", "financial", "full"),
                    metadata={
                        "stage": "rag_direct",
                        "matched_case": top_case.to_dict(),
                        "all_cases": [c.to_dict() for c in retrieved_cases[:3]]
                    }
                )

        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}", exc_info=True)
            # RAG失败继续后续流程

    # ========== Stage 4: Few-shot LLM 意图识别 ==========
    if enable_few_shot and retrieved_cases:
        try:
            llm_decision = await _few_shot_llm_route(
                ticker=ticker,
                question=question,
                history_summary=history_summary,
                retrieved_cases=retrieved_cases,
                emb_signal=emb_signal,
                rule_signal=rule_signal,
            )

            if llm_decision is not None:
                return llm_decision

        except Exception as e:
            logger.warning(f"Few-shot LLM routing failed: {e}", exc_info=True)
            # LLM失败，尝试fallback到RAG直接决策
            if high_confidence_route:
                top_case = retrieved_cases[0]
                return RoutingDecision(
                    route=high_confidence_route,
                    confidence=top_case.similarity * 0.9,  # 稍微降低置信度
                    rationale=f"Few-shot LLM失败， fallback到RAG匹配: {top_case.intent_category}",
                    source="rag_fallback",
                    embedding_signal=emb_signal,
                    rule_signal=rule_signal,
                    requires_fresh_data=high_confidence_route in ("research", "financial", "full"),
                    metadata={"stage": "rag_fallback", "error": str(e)}
                )

    # ========== Stage 5: 原始LLM路由（Fallback） ==========
    logger.info(f"Falling back to original LLM router for: {question[:50]}...")
    return await _original_llm_route(
        ticker=ticker,
        question=question,
        history_summary=history_summary,
        emb_signal=emb_signal,
        rule_signal=rule_signal,
    )


async def _few_shot_llm_route(
    ticker: str,
    question: str,
    history_summary: str,
    retrieved_cases: list[IntentCase],
    emb_signal: Optional[EmbeddingSignal],
    rule_signal: RuleSignal,
) -> Optional[RoutingDecision]:
    """使用Few-shot Prompt的LLM路由

    基于RAG召回的相似案例，构建Few-shot Prompt进行意图识别
    """
    try:
        from app.agents.llm_config import get_model_client
        from autogen_core.models import UserMessage

        # 构建Few-shot Prompt
        prompt = build_few_shot_intent_prompt(
            user_query=question,
            ticker=ticker,
            retrieved_cases=retrieved_cases,
            history_summary=history_summary,
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
        )

        logger.debug(f"Few-shot prompt built, calling LLM for intent recognition...")

        # 调用LLM
        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="enhanced_router")])
        raw_response = result.content.strip()

        # 解析响应
        parsed = parse_intent_response(raw_response)

        route: Route = parsed.get("route", "advisor_only")
        confidence_str = parsed.get("confidence", "medium")
        confidence = {"high": 0.9, "medium": 0.7, "low": 0.5}.get(confidence_str, 0.7)

        # 验证route有效性
        valid_routes = ("advisor_only", "research", "financial", "full", "unknown")
        if route not in valid_routes:
            route = "advisor_only"

        # 构建metadata
        metadata: Dict[str, Any] = {
            "stage": "few_shot_llm",
            "intent_category": parsed.get("intent_category"),
            "intent_subcategory": parsed.get("intent_subcategory"),
            "extracted_entities": parsed.get("extracted_entities", {}),
            "needs_clarification": parsed.get("needs_clarification", False),
            "retrieved_cases": [c.to_dict() for c in retrieved_cases[:3]],
        }

        # 如果需要澄清，记录澄清问题
        if parsed.get("needs_clarification"):
            metadata["clarification_question"] = parsed.get("clarification_question", "")

        return RoutingDecision(
            route=route,
            confidence=confidence,
            rationale=parsed.get("reasoning", f"Few-shot识别: {parsed.get('intent_category', 'unknown')}"),
            source="rag_few_shot_llm",
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
            requires_fresh_data=parsed.get("requires_fresh_data", route in ("research", "financial", "full")),
            metadata=metadata
        )

    except Exception as e:
        logger.error(f"Few-shot LLM route error: {e}", exc_info=True)
        return None


async def _original_llm_route(
    ticker: str,
    question: str,
    history_summary: str,
    emb_signal: Optional[EmbeddingSignal],
    rule_signal: RuleSignal,
) -> RoutingDecision:
    """原始LLM路由（作为fallback）

    保持与原router.py相同的逻辑，确保兼容性
    """
    try:
        from app.agents.llm_config import get_model_client
        from autogen_core.models import UserMessage

        # 构建证据摘要
        evidence_parts: list[str] = []
        if emb_signal and emb_signal.top_candidates:
            top3 = emb_signal.top_candidates[:3]
            evidence_parts.append(
                "Embedding相似度: " + ", ".join(f"{r}={s:.3f}" for r, s in top3)
            )
        if rule_signal.soft_scores:
            evidence_parts.append(
                "规则得分: " + ", ".join(f"{r}={s:.2f}" for r, s in rule_signal.soft_scores.items())
            )
        if rule_signal.matched_rules:
            evidence_parts.append(f"匹配规则: {rule_signal.matched_rules}")
        evidence_text = "\n".join(evidence_parts) if evidence_parts else "无前置信号"

        wrapped_question = wrap_user_input(question)

        prompt = (
            "你是一个路由分类器，用于股票分析聊天机器人。"
            "根据用户的追问，将其分类到以下路由之一:\n\n"
            "- advisor_only: 一般建议、观点、解释、澄清、总结、风险问题\n"
            "- research: 需要最新新闻、市场数据、行业趋势、竞争对手信息、催化剂\n"
            "- financial: 需要财务报表分析、估值、指标（P/E、ROE等）\n"
            "- full: 需要研究和财务数据，或全面重新分析\n"
            "- unknown: 与股票分析完全无关——闲聊、离题、问候或无法理解\n\n"
            f"股票: {ticker}\n"
            f"用户问题:\n{wrapped_question}\n"
        )

        if history_summary:
            prompt += f"\n对话上下文（近期）:\n{history_summary[:1500]}\n"

        prompt += (
            f"\n前置路由证据:\n{evidence_text}\n\n"
            "仅返回JSON对象:\n"
            '{"route": "<route>", "confidence": <0.0-1.0>, '
            '"rationale": "<简短原因>", "requires_fresh_data": <true/false>}'
        )

        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="router")])
        raw = result.content.strip()

        # 提取JSON
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        route = parsed.get("route", "advisor_only")
        if route not in ("advisor_only", "research", "financial", "full", "unknown"):
            route = "advisor_only"

        return RoutingDecision(
            route=route,
            confidence=float(parsed.get("confidence", 0.5)),
            rationale=parsed.get("rationale", "LLM分类"),
            source="llm_fallback",
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
            requires_fresh_data=parsed.get("requires_fresh_data", route != "advisor_only"),
            metadata={"stage": "original_llm"}
        )

    except Exception as e:
        logger.error(f"Original LLM route failed: {e}", exc_info=True)
        # 最终fallback
        return _fallback_decision(emb_signal, rule_signal)


def _fallback_decision(
    emb_signal: Optional[EmbeddingSignal],
    rule_signal: RuleSignal,
) -> RoutingDecision:
    """最终fallback决策"""
    route: Route = "advisor_only"
    confidence = 0.3

    if emb_signal and emb_signal.top_candidates:
        top_route, top_score = emb_signal.top_candidates[0]
        if top_score > 0.4:
            route = top_route
            confidence = top_score

    return RoutingDecision(
        route=route,
        confidence=confidence,
        rationale="Fallback: 使用embedding最高候选",
        source="fallback",
        embedding_signal=emb_signal,
        rule_signal=rule_signal,
        requires_fresh_data=route in ("research", "financial", "full"),
        metadata={"stage": "fallback"}
    )


# ========== 兼容性接口 ==========

async def route_followup(
    ticker: str,
    question: str,
    history_summary: str = "",
) -> RoutingDecision:
    """与原router.py兼容的接口

    使用增强版管线，但保持相同签名
    """
    return await enhanced_route_followup(
        ticker=ticker,
        question=question,
        history_summary=history_summary,
        enable_rag=True,
        enable_few_shot=True,
    )
