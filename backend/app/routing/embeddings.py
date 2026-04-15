"""Embedding-based coarse filter for follow-up intent routing.

Uses sentence-transformers to compute semantic similarity between the
user's follow-up question and a curated set of intent examples per route.
The model is loaded lazily and cached for the lifetime of the process.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from app.routing.types import Route, EmbeddingSignal

logger = logging.getLogger(__name__)

# Curated intent examples per route – used for semantic matching
_ROUTE_EXAMPLES: dict[Route, list[str]] = {
    "research": [
        "最近有什么新闻",
        "有什么利好消息",
        "竞争对手情况如何",
        "行业趋势是什么",
        "最新公告有哪些",
        "recent news about this stock",
        "what are the latest catalysts",
        "competitor analysis",
        "any major announcements",
        "industry outlook",
    ],
    "financial": [
        "财务报表分析",
        "估值是否合理",
        "PE是多少",
        "现金流情况",
        "营收增长趋势",
        "利润率如何",
        "资产负债表",
        "financial statements analysis",
        "what is the P/E ratio",
        "cash flow analysis",
        "revenue growth trend",
        "profit margin analysis",
        "balance sheet review",
        "ROE performance",
    ],
    "full": [
        "重新完整分析",
        "全面重新评估",
        "请再分析一次",
        "full re-analysis",
        "complete analysis again",
        "re-evaluate everything",
    ],
    "advisor_only": [
        "你觉得该买入吗",
        "总结一下投资建议",
        "风险有哪些",
        "能解释一下刚才的分析吗",
        "目标价是多少",
        "should I buy this stock",
        "summarize the investment advice",
        "what are the main risks",
        "explain the previous analysis",
        "what is the target price",
    ],
    "unknown": [
        "今天天气怎么样",
        "帮我写一首诗",
        "你是谁",
        "讲个笑话",
        "帮我翻译一段话",
        "怎么做红烧肉",
        "你好",
        "最近有什么好看的电影",
        "帮我写一段代码",
        "你的爱好是什么",
        "你有感情吗",
        "你几岁了",
        "你能做什么",
        "在吗",
        "无聊",
        "随便聊聊",
        "帮我算一道数学题",
        "推荐一家餐厅",
        "怎么减肥",
        "what's the weather today",
        "tell me a joke",
        "who are you",
        "translate this for me",
        "how to cook pasta",
        "write me a poem",
        "what are your hobbies",
        "can you feel emotions",
        "recommend a restaurant",
        "I'm bored",
        "help me with my homework",
    ],
}


class EmbeddingService:
    """Lazy-loaded sentence-transformers embedding service."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._example_embeddings: dict[Route, np.ndarray] | None = None
        self._example_texts: dict[Route, list[str]] = _ROUTE_EXAMPLES

    def _load(self) -> bool:
        """Load the model.  Returns True if successful."""
        if self._model is not None:
            return True
        try:
            # Try to use HF mirror for China users
            import os
            if not os.environ.get("HF_ENDPOINT"):
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            self._precompute_examples()
            logger.info("Embedding model '%s' loaded.", self._model_name)
            return True
        except Exception:
            logger.warning(
                "Failed to load embedding model '%s'. Embedding stage will be skipped.",
                self._model_name,
                exc_info=True,
            )
            return False

    def _precompute_examples(self) -> None:
        if self._model is None:
            return
        self._example_embeddings = {}
        for route, texts in self._example_texts.items():
            self._example_embeddings[route] = self._model.encode(
                texts, normalize_embeddings=True,
            )

    def compute_signal(self, query: str, ticker: str = "") -> Optional[EmbeddingSignal]:
        """Compute embedding similarity against intent examples.

        Returns None if the model is unavailable (graceful fallback).
        """
        if not self._load():
            return None

        # Prepend ticker for context (lightweight alternative to query rewriting)
        enriched = f"{ticker}: {query}" if ticker else query
        query_vec = self._model.encode([enriched], normalize_embeddings=True)[0]

        route_scores: dict[Route, float] = {}
        matched_examples: list[tuple[str, float]] = []

        for route, embeddings in self._example_embeddings.items():
            similarities = embeddings @ query_vec  # cosine similarity (normalised)
            max_idx = int(np.argmax(similarities))
            max_sim = float(similarities[max_idx])
            route_scores[route] = max_sim
            matched_examples.append((self._example_texts[route][max_idx], max_sim))

        top_candidates = sorted(route_scores.items(), key=lambda x: x[1], reverse=True)
        matched_examples.sort(key=lambda x: x[1], reverse=True)

        return EmbeddingSignal(
            top_candidates=top_candidates,
            matched_examples=matched_examples[:5],
        )

    def encode(self, text: str) -> list[float] | None:
        """Return the raw embedding vector for *text*, or None if model unavailable."""
        if not self._load():
            return None
        vec = self._model.encode([text], normalize_embeddings=True)[0]
        return vec.tolist()


# Module-level singleton
_service: EmbeddingService | None = None


def get_embedding_service(model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService(model_name)
    return _service
