"""RAG意图召回层 - 基于pgvector的意图案例检索

复用现有的embedding服务和存储层，提供意图知识的向量检索能力。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import numpy as np

from app.routing.embeddings import get_embedding_service
from app.routing.intent_knowledge_base import INTENT_KNOWLEDGE_CASES

logger = logging.getLogger(__name__)


@dataclass
class IntentCase:
    """检索到的意图案例"""
    query: str
    intent_category: str
    intent_subcategory: str
    route: str
    handling_strategy: str
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    difficulty: str = "standard"
    common_variations: List[str] = field(default_factory=list)
    similarity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "query": self.query,
            "intent_category": self.intent_category,
            "intent_subcategory": self.intent_subcategory,
            "route": self.route,
            "handling_strategy": self.handling_strategy,
            "similarity": self.similarity,
            "difficulty": self.difficulty,
        }


class RAGIntentRetriever:
    """RAG意图召回器

    支持两种模式：
    1. 内存模式：直接使用预加载的意图知识库（适合冷启动，无需数据库）
    2. 数据库模式：从pgvector检索（适合大规模知识库，支持动态更新）
    """

    def __init__(self, use_memory_mode: bool = True):
        self.embedding_service = get_embedding_service()
        self.use_memory_mode = use_memory_mode

        # 内存模式：预计算所有案例的embedding
        self._memory_cases: List[IntentCase] = []
        self._memory_embeddings: Optional[np.ndarray] = None

        if use_memory_mode:
            self._load_memory_index()

    def _load_memory_index(self) -> None:
        """内存模式：预加载意图知识库并计算embedding"""
        logger.info("Loading intent knowledge base into memory...")

        try:
            # 将知识库转换为IntentCase对象
            self._memory_cases = []
            queries = []

            for case_data in INTENT_KNOWLEDGE_CASES:
                case = IntentCase(
                    query=case_data["query"],
                    intent_category=case_data["intent_category"],
                    intent_subcategory=case_data["intent_subcategory"],
                    route=case_data["route"],
                    handling_strategy=case_data["handling_strategy"],
                    extracted_entities=case_data.get("extracted_entities", {}),
                    difficulty=case_data.get("difficulty", "standard"),
                    common_variations=case_data.get("common_variations", []),
                    metadata=case_data
                )
                self._memory_cases.append(case)
                queries.append(case_data["query"])

                # 同时索引常见变体，增加召回率
                for variation in case_data.get("common_variations", [])[:2]:  # 每种只取前2个变体
                    variation_case = IntentCase(
                        query=variation,
                        intent_category=case_data["intent_category"],
                        intent_subcategory=case_data["intent_subcategory"],
                        route=case_data["route"],
                        handling_strategy=case_data["handling_strategy"],
                        extracted_entities=case_data.get("extracted_entities", {}),
                        difficulty=case_data.get("difficulty", "standard"),
                        similarity=0.0,
                        metadata={"is_variation": True, "parent_query": case_data["query"]}
                    )
                    self._memory_cases.append(variation_case)
                    queries.append(variation)

            # 批量计算embedding
            if queries:
                # 延迟加载模型
                if not self.embedding_service._load():
                    logger.warning("Embedding model not available, RAG retriever will be disabled")
                    return

                embeddings = self.embedding_service._model.encode(
                    queries,
                    normalize_embeddings=True
                )
                self._memory_embeddings = embeddings

            logger.info(f"Loaded {len(self._memory_cases)} intent cases into memory")

        except Exception as e:
            logger.error(f"Failed to load memory index: {e}", exc_info=True)
            self._memory_cases = []
            self._memory_embeddings = None

    async def retrieve_similar_intents(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        diversify: bool = True
    ) -> List[IntentCase]:
        """召回相似意图案例

        Args:
            query: 用户查询
            top_k: 召回数量
            similarity_threshold: 相似度阈值
            diversify: 是否对结果进行去重（同一意图类别只保留最高相似度的一个）

        Returns:
            相似意图案例列表（按相似度降序）
        """
        if self.use_memory_mode:
            return self._retrieve_from_memory(query, top_k, similarity_threshold, diversify)
        else:
            return await self._retrieve_from_database(query, top_k, similarity_threshold)

    def _retrieve_from_memory(
        self,
        query: str,
        top_k: int,
        threshold: float,
        diversify: bool
    ) -> List[IntentCase]:
        """从内存检索相似案例"""
        if not self._memory_cases or self._memory_embeddings is None:
            logger.debug("Memory index not available, skipping RAG retrieval")
            return []

        try:
            # 编码用户查询
            query_vec = self.embedding_service._model.encode(
                [query],
                normalize_embeddings=True
            )[0]

            # 计算余弦相似度
            similarities = self._memory_embeddings @ query_vec  # shape: (n_cases,)

            # 过滤并排序
            case_scores = []
            for idx, sim in enumerate(similarities):
                if sim >= threshold:
                    case_scores.append((idx, float(sim)))

            # 按相似度降序排序
            case_scores.sort(key=lambda x: x[1], reverse=True)

            # 构建结果
            results = []
            seen_categories = set() if diversify else None

            for idx, sim in case_scores:
                case = self._memory_cases[idx]

                # 去重：同一意图子类别只保留最相似的
                if diversify:
                    category_key = f"{case.intent_category}:{case.intent_subcategory}"
                    if category_key in seen_categories:
                        continue
                    seen_categories.add(category_key)

                # 创建新的实例，避免修改原始数据
                result_case = IntentCase(
                    query=case.query,
                    intent_category=case.intent_category,
                    intent_subcategory=case.intent_subcategory,
                    route=case.route,
                    handling_strategy=case.handling_strategy,
                    extracted_entities=case.extracted_entities.copy(),
                    difficulty=case.difficulty,
                    common_variations=case.common_variations.copy(),
                    similarity=sim,
                    metadata=case.metadata.copy()
                )
                results.append(result_case)

                if len(results) >= top_k:
                    break

            logger.debug(f"RAG retrieved {len(results)} intent cases for query: {query[:30]}...")
            return results

        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}", exc_info=True)
            return []

    async def _retrieve_from_database(
        self,
        query: str,
        top_k: int,
        threshold: float
    ) -> List[IntentCase]:
        """从数据库检索相似案例（待实现）

        如果需要大规模知识库或动态更新，可以实现此模式
        """
        # TODO: 实现pgvector数据库检索
        # 需要依赖storage层提供search_intent_cases方法
        logger.warning("Database mode not implemented, falling back to memory mode")
        return self._retrieve_from_memory(query, top_k, threshold, True)

    def group_by_intent_category(self, cases: List[IntentCase]) -> Dict[str, List[IntentCase]]:
        """按意图类别分组"""
        grouped: Dict[str, List[IntentCase]] = {}
        for case in cases:
            key = case.intent_category
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(case)
        return grouped

    def get_high_confidence_route(
        self,
        cases: List[IntentCase],
        threshold: float = 0.75
    ) -> Optional[str]:
        """获取高置信度的路由决策

        如果top case的相似度超过阈值，直接返回对应route
        用于快速路径，跳过LLM判断
        """
        if not cases:
            return None

        top_case = cases[0]
        if top_case.similarity >= threshold:
            logger.debug(f"High confidence route: {top_case.route} (sim={top_case.similarity:.3f})")
            return top_case.route

        return None

    def build_intent_summary(self, cases: List[IntentCase]) -> str:
        """构建意图召回的摘要信息（用于prompt）"""
        if not cases:
            return "未找到相似意图案例"

        lines = ["相似意图召回结果："]
        for i, case in enumerate(cases[:3], 1):
            lines.append(
                f"{i}. [{case.intent_category}/{case.intent_subcategory}] "
                f"相似度: {case.similarity:.2f} | 示例: \"{case.query}\" | 路由: {case.route}"
            )
        return "\n".join(lines)


# 全局单例
_retriever_instance: Optional[RAGIntentRetriever] = None


def get_rag_retriever(use_memory_mode: bool = True) -> RAGIntentRetriever:
    """获取RAG意图召回器单例"""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = RAGIntentRetriever(use_memory_mode=use_memory_mode)
    return _retriever_instance


async def retrieve_intent_cases(
    query: str,
    top_k: int = 5,
    threshold: float = 0.5
) -> List[IntentCase]:
    """便捷的召回函数"""
    retriever = get_rag_retriever()
    return await retriever.retrieve_similar_intents(query, top_k, threshold)
