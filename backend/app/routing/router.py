"""Hybrid routing pipeline: embedding → rules → LLM → decision.

Orchestrates the three routing stages and returns a single RoutingDecision.
Hard rules short-circuit immediately.  High-confidence soft rules also
skip the LLM call to save latency.  Otherwise the LLM acts as final arbiter.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.routing.types import Route, RoutingDecision, EmbeddingSignal, RuleSignal
from app.routing.embeddings import get_embedding_service
from app.routing.rules import evaluate_rules
from app.config import settings
from app.utils.prompt_boundary import wrap_user_input

logger = logging.getLogger(__name__)

# If soft-rule top score ≥ this value, skip the LLM router
_RULE_CONFIDENCE_THRESHOLD = 0.7


async def route_followup(
    ticker: str,
    question: str,
    history_summary: str = "",
) -> RoutingDecision:
    """Run the full routing pipeline and return a structured decision.

    Pipeline: embedding coarse filter → rules → LLM router (if needed).
    """

    # Stage 1: Embedding coarse filter
    emb_service = get_embedding_service(settings.EMBEDDING_MODEL)
    emb_signal = emb_service.compute_signal(query=question, ticker=ticker)

    # Stage 2: Rules
    rule_signal = evaluate_rules(question)

    # Hard rule override — skip LLM
    if rule_signal.hard_route is not None:
        return RoutingDecision(
            route=rule_signal.hard_route,
            confidence=1.0,
            rationale=f"Hard rule matched: {rule_signal.matched_rules}",
            source="hard_rule",
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
            requires_fresh_data=rule_signal.hard_route in ("research", "financial", "full"),
        )

    # Strong soft rule — skip LLM if confident enough
    if rule_signal.soft_scores:
        best_route = max(rule_signal.soft_scores, key=rule_signal.soft_scores.get)
        best_score = rule_signal.soft_scores[best_route]
        if best_score >= _RULE_CONFIDENCE_THRESHOLD:
            return RoutingDecision(
                route=best_route,
                confidence=best_score,
                rationale=f"Soft rules confident: {rule_signal.matched_rules}",
                source="soft_rule",
                embedding_signal=emb_signal,
                rule_signal=rule_signal,
                requires_fresh_data=best_route in ("research", "financial", "full"),
            )

    # Stage 3: LLM router
    llm_decision = await _llm_route(
        ticker=ticker,
        question=question,
        history_summary=history_summary,
        emb_signal=emb_signal,
        rule_signal=rule_signal,
    )

    if llm_decision is not None:
        return llm_decision

    # Fallback: use embedding top candidate or default to advisor_only
    return _fallback_decision(emb_signal, rule_signal)


# ── LLM Router ──────────────────────────────────────────────────────

async def _llm_route(
    ticker: str,
    question: str,
    history_summary: str,
    emb_signal: Optional[EmbeddingSignal],
    rule_signal: RuleSignal,
) -> Optional[RoutingDecision]:
    """Use the LLM to make the final routing decision."""
    try:
        from app.agents.llm_config import get_model_client
        from autogen_core.models import UserMessage

        # Build evidence summary for the prompt
        evidence_parts: list[str] = []
        if emb_signal and emb_signal.top_candidates:
            top3 = emb_signal.top_candidates[:3]
            evidence_parts.append(
                "Embedding similarities: "
                + ", ".join(f"{r}={s:.3f}" for r, s in top3)
            )
        if rule_signal.soft_scores:
            evidence_parts.append(
                "Rule scores: "
                + ", ".join(f"{r}={s:.2f}" for r, s in rule_signal.soft_scores.items())
            )
        if rule_signal.matched_rules:
            evidence_parts.append(f"Matched rules: {rule_signal.matched_rules}")
        evidence_text = "\n".join(evidence_parts) if evidence_parts else "No prior signals."

        wrapped_question = wrap_user_input(question)

        prompt = (
            "You are a routing classifier for a stock analysis chatbot.\n"
            "Given a user's follow-up question about a stock, classify it into one of these routes:\n\n"
            "- advisor_only: General advice, opinion, explanation, clarification, summary, risk questions\n"
            "- research: Needs fresh news, market data, industry trends, competitor info, catalysts\n"
            "- financial: Needs financial statement analysis, valuation, metrics (P/E, ROE, etc.)\n"
            "- full: Needs both research AND financial data, or a comprehensive re-analysis\n"
            "- unknown: Not related to stock analysis at all — chitchat, off-topic, greetings, or unintelligible\n\n"
            f"Stock: {ticker}\n"
            f"User Question:\n{wrapped_question}\n"
        )

        if history_summary:
            prompt += f"\nConversation context (recent):\n{history_summary[:1500]}\n"

        prompt += (
            f"\nPrior routing evidence:\n{evidence_text}\n\n"
            "Respond with ONLY a JSON object:\n"
            '{"route": "<route>", "confidence": <0.0-1.0>, '
            '"rationale": "<brief reason>", "requires_fresh_data": <true/false>}'
        )

        client = get_model_client()
        result = await client.create([UserMessage(content=prompt, source="router")])
        raw = result.content.strip()

        # Extract JSON from response (may have markdown fences)
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
            rationale=parsed.get("rationale", "LLM classification"),
            source="llm",
            embedding_signal=emb_signal,
            rule_signal=rule_signal,
            requires_fresh_data=parsed.get("requires_fresh_data", route != "advisor_only"),
        )

    except Exception:
        logger.warning("LLM router failed, falling back.", exc_info=True)
        return None


# ── Fallback ─────────────────────────────────────────────────────────

def _fallback_decision(
    emb_signal: Optional[EmbeddingSignal],
    rule_signal: RuleSignal,
) -> RoutingDecision:
    """Fallback when LLM router fails — use embedding top candidate or default."""
    route: Route = "unknown"
    confidence = 0.3

    if emb_signal and emb_signal.top_candidates:
        top_route, top_score = emb_signal.top_candidates[0]
        if top_score > 0.4:
            route = top_route
            confidence = top_score

    return RoutingDecision(
        route=route,
        confidence=confidence,
        rationale="Fallback: LLM unavailable, used embedding top candidate",
        source="fallback",
        embedding_signal=emb_signal,
        rule_signal=rule_signal,
        requires_fresh_data=route in ("research", "financial", "full"),
    )
