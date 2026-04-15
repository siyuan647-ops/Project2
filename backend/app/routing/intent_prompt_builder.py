"""Few-shot Prompt构建器 - 基于RAG召回的意图识别Prompt

构建包含相似案例的Few-shot Prompt，指导LLM进行准确的意图识别。
"""

import logging
from typing import List, Dict, Any, Optional
import json

import tiktoken

from app.routing.rag_intent_retriever import IntentCase
from app.routing.types import EmbeddingSignal, RuleSignal
from app.utils.prompt_boundary import wrap_user_input

logger = logging.getLogger(__name__)

# 使用cl100k_base编码（支持GPT-4/GPT-3.5-turbo）
ENCODING = tiktoken.get_encoding("cl100k_base")

# Token预算配置（总计2500 tokens）
MAX_TOTAL_TOKENS = 2500   # Prompt总token上限
RESERVED_TOKENS = 500     # 保留给输出和JSON格式
MAX_HISTORY_TOKENS = 500  # history_summary最大token数
MAX_CASE_TOKENS = 400     # 单个case最大token数


def count_tokens(text: str) -> int:
    """计算文本的token数量"""
    if not text:
        return 0
    return len(ENCODING.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """将文本截断到指定token数"""
    if not text:
        return text
    tokens = ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = ENCODING.decode(tokens[:max_tokens])
    return truncated + "...[截断]"


def estimate_prompt_tokens(
    intent_definitions: str,
    few_shot_section: str,
    evidence_section: str,
    user_query: str,
    ticker: str,
    history_summary: str
) -> int:
    """估算完整prompt的token数"""
    # 基础模板token（估算）
    base_template = 150

    total = (
        base_template +
        count_tokens(intent_definitions) +
        count_tokens(few_shot_section) +
        count_tokens(evidence_section) +
        count_tokens(user_query) +
        count_tokens(ticker) +
        count_tokens(history_summary)
    )
    return total


def build_few_shot_intent_prompt(
    user_query: str,
    ticker: str,
    retrieved_cases: List[IntentCase],
    history_summary: str = "",
    embedding_signal: Optional[EmbeddingSignal] = None,
    rule_signal: Optional[RuleSignal] = None
) -> str:
    """构建包含RAG召回案例的Few-shot意图识别Prompt（带Token精准控制）

    Args:
        user_query: 用户当前查询
        ticker: 股票代码
        retrieved_cases: RAG召回的相似案例
        history_summary: 对话历史摘要
        embedding_signal: embedding粗筛信号（可选）
        rule_signal: 规则引擎信号（可选）

    Returns:
        完整的Few-shot Prompt
    """

    # 1. Token控制：截断history_summary
    if history_summary:
        history_summary = truncate_to_tokens(history_summary, MAX_HISTORY_TOKENS)
        history_section = f"\n对话历史摘要: {history_summary}"
    else:
        history_section = ""

    # 2. 计算可用token预算
    available_tokens = MAX_TOTAL_TOKENS - RESERVED_TOKENS - count_tokens(history_section)

    # 3. 构建固定部分（意图定义）
    intent_definitions = _build_intent_definitions()
    intent_def_tokens = count_tokens(intent_definitions)

    # 4. 构建证据部分
    evidence_section = _build_evidence_summary(embedding_signal, rule_signal)
    evidence_tokens = count_tokens(evidence_section)

    # 5. 计算Few-shot部分的预算
    few_shot_budget = available_tokens - intent_def_tokens - evidence_tokens - 200  # 200为缓冲

    # 6. Token感知的案例选择
    diverse_cases = _select_diverse_cases_token_aware(
        retrieved_cases,
        max_tokens=max(few_shot_budget, MAX_CASE_TOKENS)  # 至少保证1个case的预算
    )

    # 7. 构建Few-shot部分
    few_shot_section = _build_few_shot_examples(diverse_cases)

    # 8. 估算总token并动态调整
    wrapped_query = wrap_user_input(user_query)
    estimated_tokens = estimate_prompt_tokens(
        intent_definitions, few_shot_section, evidence_section,
        user_query, ticker, history_section
    )

    # 如果超过预算，减少case数量
    while estimated_tokens > available_tokens and len(diverse_cases) > 0:
        diverse_cases = diverse_cases[:-1]  # 移除最后一个case
        few_shot_section = _build_few_shot_examples(diverse_cases)
        estimated_tokens = estimate_prompt_tokens(
            intent_definitions, few_shot_section, evidence_section,
            user_query, ticker, history_section
        )

    # 如果仍然超过，截断few_shot_section
    if estimated_tokens > available_tokens and few_shot_section:
        max_few_shot_tokens = available_tokens - intent_def_tokens - evidence_tokens - 100
        few_shot_section = truncate_to_tokens(few_shot_section, max_few_shot_tokens)

    # 9. 组装完整Prompt
    prompt = f"""你是一个专业的金融投资意图识别助手。你的任务是分析用户的查询意图，并参考相似案例做出准确判断。

{intent_definitions}

{few_shot_section}

{evidence_section}

=== 当前任务 ===
股票代码: {ticker}
用户Query: {wrapped_query}
{history_section}
请分析用户意图，并以JSON格式输出：
{{
    "intent_category": "意图主类别",
    "intent_subcategory": "意图子类别",
    "route": "路由决策(financial/research/advisor_only/full/unknown)",
    "confidence": "置信度(high/medium/low)",
    "extracted_entities": {{"提取的关键实体": "值"}},
    "needs_clarification": "是否需要澄清(true/false)",
    "clarification_question": "如需要澄清，提供一个具体的澄清问题",
    "reasoning": "判断理由(简洁，50字以内)"
}}

判断指引：
1. 如果用户Query意图不明确（如"这个怎么样"），设置needs_clarification为true并提供澄清问题
2. 如果涉及多个方面（如既问财务又问新闻），route应为"full"
3. 如果是非股票相关问题（天气、计算、加密货币等），route为"unknown"
4. 如果RAG召回的案例相似度很高(>0.8)，优先遵循其意图分类
5. 结合embedding和规则引擎的证据综合判断

只输出JSON，不要有任何其他文字。"""

    # 记录Token使用情况
    final_tokens = count_tokens(prompt)
    logger.debug(
        f"Stage 4 prompt built: {final_tokens} tokens, "
        f"{len(diverse_cases)} cases used, "
        f"history: {count_tokens(history_summary)} tokens"
    )

    return prompt


def _select_diverse_cases(cases: List[IntentCase], max_cases: int = 3) -> List[IntentCase]:
    """选择多样化的案例，避免同一意图类别重复"""
    if not cases:
        return []

    selected = []
    seen_categories = set()

    # 优先选择不同类别的案例
    for case in cases:
        category_key = f"{case.intent_category}:{case.intent_subcategory}"
        if category_key not in seen_categories:
            selected.append(case)
            seen_categories.add(category_key)

        if len(selected) >= max_cases:
            break

    # 如果不够，补充相似度最高的
    if len(selected) < max_cases:
        for case in cases:
            if case not in selected:
                selected.append(case)
            if len(selected) >= max_cases:
                break

    return selected


def _select_diverse_cases_token_aware(
    cases: List[IntentCase],
    max_tokens: int = MAX_CASE_TOKENS * 3
) -> List[IntentCase]:
    """选择多样化的案例，同时控制总token数"""
    if not cases:
        return []

    selected = []
    seen_categories = set()
    current_tokens = 0

    # 优先选择不同类别的案例
    for case in cases:
        category_key = f"{case.intent_category}:{case.intent_subcategory}"

        # 估算这个case的token数
        case_text = f"{case.query} {case.handling_strategy} {case.extracted_entities}"
        case_tokens = count_tokens(case_text)

        if category_key not in seen_categories:
            if current_tokens + case_tokens <= max_tokens:
                selected.append(case)
                seen_categories.add(category_key)
                current_tokens += case_tokens

        if len(selected) >= 3 or current_tokens >= max_tokens:
            break

    # 如果token预算还有剩余，补充相似度最高的
    if current_tokens < max_tokens:
        for case in cases:
            if case not in selected:
                case_text = f"{case.query} {case.handling_strategy}"
                case_tokens = count_tokens(case_text)

                if current_tokens + case_tokens <= max_tokens:
                    selected.append(case)
                    current_tokens += case_tokens
                else:
                    break

            if len(selected) >= 3:
                break

    return selected


def _build_few_shot_examples(cases: List[IntentCase]) -> str:
    """构建Few-shot示例部分"""
    if not cases:
        return "=== 相似案例参考 ===\n无高相似度案例\n"

    examples = []
    for i, case in enumerate(cases, 1):
        example = f"""
【相似案例{i}】
用户Query: "{case.query}"
意图类别: {case.intent_category} / {case.intent_subcategory}
建议路由: {case.route}
处理策略: {case.handling_strategy}
相似度: {case.similarity:.2f}"""

        # 添加实体提取示例（如果有）
        if case.extracted_entities:
            entities_str = json.dumps(case.extracted_entities, ensure_ascii=False)
            example += f"\n提取实体: {entities_str}"

        examples.append(example)

    return "=== 相似案例参考 ===" + "".join(examples)


def _build_evidence_summary(
    embedding_signal: Optional[EmbeddingSignal],
    rule_signal: Optional[RuleSignal]
) -> str:
    """构建路由管线证据摘要"""
    parts = []

    if embedding_signal and embedding_signal.top_candidates:
        top3 = embedding_signal.top_candidates[:3]
        parts.append("Embedding相似度: " + ", ".join(f"{r}={s:.3f}" for r, s in top3))

    if rule_signal:
        if rule_signal.matched_rules:
            parts.append(f"匹配规则: {', '.join(rule_signal.matched_rules)}")
        if rule_signal.soft_scores:
            parts.append("规则得分: " + ", ".join(f"{r}={s:.2f}" for r, s in rule_signal.soft_scores.items()))

    if parts:
        return "=== 路由管线证据 ===\n" + "\n".join(parts)
    return ""


def _build_intent_definitions() -> str:
    """构建意图类别定义"""
    return """=== 意图类别定义 ===

【财务指标类 - financial】
- financial_metrics: 财务指标查询（PE、ROE、EPS、现金流等）
- financial_risk: 财务风险评估（亏损担忧、应收账款、存货、负债等）
- financial_trend: 财务趋势分析（连续变化、同比环比等）

【研究分析类 - research】
- news_catalyst: 新闻事件影响（利好利空、催化剂等）
- competitive_analysis: 竞争对比分析（与对手比较、行业格局等）
- macro_impact: 宏观政策影响（利率、政策、行业趋势等）
- management_change: 管理层变动
- moat_analysis: 护城河分析
- institutional_activity: 机构持仓变化

【投资建议类 - advisor_only】
- investment_timing: 投资择时建议（买入时机、等待等）
- position_management: 仓位管理（止损、加仓、减仓等）
- risk_assessment: 风险评估（集中度、波动性匹配等）
- summary_request: 总结请求（投资亮点、风险等）
- valuation_concern: 估值担忧（高估值、上涨空间等）

【综合分析类 - full】
- multi_factor: 多因素综合（需要完整分析）
- vague_request: 模糊请求（如"分析一下"）

【其他类】
- ambiguous: 意图不明确（需要澄清）
- unknown: 非股票相关问题（天气、计算、加密货币等）"""


def build_clarification_prompt(
    user_query: str,
    ticker: str,
    possible_intents: List[str]
) -> str:
    """构建澄清问题的Prompt

    当意图不明确时，生成一个引导性问题帮助用户明确需求
    """
    intent_options = {
        "financial": "查看具体财务指标（PE、ROE、现金流等）",
        "research": "了解最新新闻和行业动态",
        "advisor_only": "获得投资建议（买入时机、风险评估等）",
        "full": "进行完整综合分析"
    }

    options_text = "\n".join(
        f"- {intent_options.get(intent, intent)}"
        for intent in possible_intents[:3]
        if intent in intent_options
    )

    wrapped_query = wrap_user_input(user_query)

    prompt = f"""用户Query意图不够明确。请生成一个简洁的澄清问题，引导用户明确他们想了解的内容。

股票: {ticker}
用户Query: {wrapped_query}

可能的意图方向：
{options_text}

请生成一个友好的澄清问题（50字以内），帮助用户明确需求。直接输出问题文本，不要有其他内容。"""

    return prompt


def parse_intent_response(raw_response: str) -> Dict[str, Any]:
    """解析LLM的意图识别响应

    Args:
        raw_response: LLM返回的原始文本

    Returns:
        解析后的字典，如果解析失败返回默认值
    """
    try:
        # 提取JSON部分（处理可能的markdown代码块）
        text = raw_response.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()

        # 尝试解析JSON
        parsed = json.loads(text)

        # 验证并设置默认值
        result = {
            "intent_category": parsed.get("intent_category", "ambiguous"),
            "intent_subcategory": parsed.get("intent_subcategory", "unclear_intent"),
            "route": parsed.get("route", "advisor_only"),
            "confidence": parsed.get("confidence", "medium"),
            "extracted_entities": parsed.get("extracted_entities", {}),
            "needs_clarification": parsed.get("needs_clarification", False),
            "clarification_question": parsed.get("clarification_question", ""),
            "reasoning": parsed.get("reasoning", ""),
        }

        # 验证route有效性
        valid_routes = ("advisor_only", "research", "financial", "full", "unknown")
        if result["route"] not in valid_routes:
            result["route"] = "advisor_only"

        return result

    except json.JSONDecodeError as e:
        # JSON解析失败，尝试提取关键信息
        return {
            "intent_category": "ambiguous",
            "intent_subcategory": "parse_error",
            "route": "advisor_only",
            "confidence": "low",
            "extracted_entities": {},
            "needs_clarification": True,
            "clarification_question": "请问您想了解财务数据、最新新闻，还是投资建议？",
            "reasoning": f"响应解析失败: {str(e)}",
            "raw_response": raw_response[:200]  # 保留原始响应用于调试
        }

    except Exception as e:
        return {
            "intent_category": "ambiguous",
            "intent_subcategory": "error",
            "route": "advisor_only",
            "confidence": "low",
            "extracted_entities": {},
            "needs_clarification": False,
            "clarification_question": "",
            "reasoning": f"处理失败: {str(e)}",
            "raw_response": raw_response[:200]
        }
