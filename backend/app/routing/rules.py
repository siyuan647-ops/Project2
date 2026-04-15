"""Rule-based routing with hard overrides and soft hints.

Hard rules fire deterministically and bypass subsequent pipeline stages.
Soft rules contribute weighted scores that inform the LLM router or
serve as the final decision when their confidence exceeds the threshold.
"""

from __future__ import annotations

import re

from app.routing.types import Route, RuleSignal

# ── Hard rules: matched → route is determined immediately ────────────

_HARD_RULES: list[tuple[str, Route, re.Pattern]] = [
    (
        "full_reanalyze",
        "full",
        re.compile(
            r"(重新|再次|再来|重做).{0,4}(分析|评估|研究)"
            r"|(完整|全面|全部).{0,4}(分析|评估|研究)"
            r"|re-?analy[sz]e|full\s+analysis|start\s+over",
            re.IGNORECASE,
        ),
    ),
]

# ── Soft rules: contribute weighted scores ───────────────────────────

_SOFT_RULES: list[tuple[str, Route, re.Pattern, float]] = [
    (
        "news_keywords",
        "research",
        re.compile(
            r"新闻|news|消息面?|最新消息|最近动态|公告|announcement"
            r"|利好|利空|催化|catalyst|事件|行业|industry"
            r"|竞争|competitor|竞品|对手|市场动态|市场趋势",
            re.IGNORECASE,
        ),
        0.7,
    ),
    (
        "financial_keywords",
        "financial",
        re.compile(
            r"财报|财务|估值|valuation|现金流|cash\s*flow"
            r"|利润|revenue|profit|营收|资产负债|balance\s*sheet"
            r"|p/?e|eps|roe|roa|毛利|净利|gross\s*margin"
            r"|股息|dividend|分红|回购|buyback"
            r"|负债率|debt|杠杆|leverage",
            re.IGNORECASE,
        ),
        0.7,
    ),
    (
        "mixed_request",
        "full",
        re.compile(
            r"(新闻|消息|行业|news).{0,20}(财务|估值|财报|valuation)"
            r"|(财务|估值|财报|valuation).{0,20}(新闻|消息|行业|news)",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        "advice_keywords",
        "advisor_only",
        re.compile(
            r"建议|advic[e\-]|推荐|recommend|买入|卖出|持有"
            r"|buy|sell|hold|目标价|target\s*price"
            r"|解释|explain|总结|summar|clarif"
            r"|风险|risk|止损|stop.?loss|仓位|position",
            re.IGNORECASE,
        ),
        0.5,
    ),
]


def evaluate_rules(question: str) -> RuleSignal:
    """Evaluate all rules against the question and return structured signals."""

    # Check hard rules first
    for rule_name, route, pattern in _HARD_RULES:
        if pattern.search(question):
            return RuleSignal(
                hard_route=route,
                soft_scores={route: 1.0},
                matched_rules=[rule_name],
            )

    # Evaluate soft rules
    soft_scores: dict[Route, float] = {}
    matched: list[str] = []

    for rule_name, route, pattern, weight in _SOFT_RULES:
        if pattern.search(question):
            current = soft_scores.get(route, 0.0)
            soft_scores[route] = min(current + weight, 1.0)
            matched.append(rule_name)

    # If both research and financial fire, escalate to full
    if soft_scores.get("research", 0) > 0 and soft_scores.get("financial", 0) > 0:
        soft_scores["full"] = max(soft_scores.get("full", 0), 0.8)
        matched.append("auto_escalate_to_full")

    return RuleSignal(
        hard_route=None,
        soft_scores=soft_scores,
        matched_rules=matched,
    )
