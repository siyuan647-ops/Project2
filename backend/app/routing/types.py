"""Routing domain types for the hybrid intent routing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any

Route = Literal["advisor_only", "research", "financial", "full", "unknown"]


@dataclass
class EmbeddingSignal:
    """Output from the embedding coarse-filter stage."""

    top_candidates: list[tuple[Route, float]] = field(default_factory=list)
    matched_examples: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class RuleSignal:
    """Output from the rules stage."""

    hard_route: Route | None = None
    soft_scores: dict[Route, float] = field(default_factory=dict)
    matched_rules: list[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    """Final structured output of the routing pipeline."""

    route: Route
    confidence: float
    rationale: str
    source: str  # "hard_rule", "soft_rule", "llm", "fallback", "rag_few_shot_llm", "rag_direct"
    embedding_signal: EmbeddingSignal | None = None
    rule_signal: RuleSignal | None = None
    requires_fresh_data: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展字段，存储RAG召回案例、实体等
