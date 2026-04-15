"""阈值调优脚本 - 寻找最优的阈值配置

通过网格搜索不同的阈值组合，评估以下指标：
- 准确率 (Accuracy)
- 成本效率 (正确决策中跳过LLM的比例)
- 平均延迟
- LLM调用次数

使用方法:
    python threshold_tuner.py --samples 100 --output threshold_results.json
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from collections import defaultdict
import argparse

sys.path.insert(0, str(Path(__file__).parent))

from app.routing import enhanced_route_followup
from app.routing.types import RoutingDecision


@dataclass
class TestCase:
    """测试用例"""
    query: str
    expected_route: str
    category: str
    difficulty: str = "standard"  # easy, standard, hard, ambiguous


@dataclass
class ThresholdConfig:
    """阈值配置"""
    rule_threshold: float
    rag_high_threshold: float
    rag_low_threshold: float

    def to_key(self) -> str:
        return f"r{self.rule_threshold:.2f}_h{self.rag_high_threshold:.2f}_l{self.rag_low_threshold:.2f}"


@dataclass
class EvaluationResult:
    """评估结果"""
    config: ThresholdConfig
    total_cases: int
    correct_predictions: int
    llm_calls: int
    rag_direct_hits: int
    rule_direct_hits: int
    total_latency_ms: float
    accuracy: float
    cost_efficiency: float  # 正确决策中跳过LLM的比例
    avg_latency_ms: float


# 扩展测试集（覆盖6大类别，不同难度）
EXPANDED_TEST_SET: list[TestCase] = [
    # ========== 财务指标类 (financial) ==========
    {"query": "PE是多少？", "expected_route": "financial", "category": "财务指标", "difficulty": "easy"},
    {"query": "AAPL的市盈率是多少，和同行业比怎么样？", "expected_route": "financial", "category": "财务指标", "difficulty": "standard"},
    {"query": "这家公司的ROE为什么比去年下降了？", "expected_route": "financial", "category": "财务指标", "difficulty": "standard"},
    {"query": "自由现金流和经营现金流有什么区别？", "expected_route": "financial", "category": "财务指标", "difficulty": "hard"},
    {"query": "毛利率连续三个季度下滑说明什么？", "expected_route": "financial", "category": "财务指标", "difficulty": "hard"},
    {"query": "EPS同比增长率怎么算？", "expected_route": "financial", "category": "财务指标", "difficulty": "standard"},
    {"query": "负债率多少算健康？", "expected_route": "financial", "category": "财务指标", "difficulty": "standard"},
    {"query": "股息率怎么样？", "expected_route": "financial", "category": "财务指标", "difficulty": "easy"},

    # ========== 财务风险类 (financial - risk) ==========
    {"query": "这家公司有没有财务造假风险？", "expected_route": "financial", "category": "财务风险", "difficulty": "hard"},
    {"query": "应收账款增长比收入还快，正常吗？", "expected_route": "financial", "category": "财务风险", "difficulty": "hard"},
    {"query": "存货周转天数增加意味着什么？", "expected_route": "financial", "category": "财务风险", "difficulty": "standard"},
    {"query": "大股东最近有减持吗？", "expected_route": "research", "category": "财务风险", "difficulty": "standard"},
    {"query": "审计报告有没有保留意见？", "expected_route": "financial", "category": "财务风险", "difficulty": "hard"},
    {"query": "短期偿债能力怎么样？", "expected_route": "financial", "category": "财务风险", "difficulty": "standard"},

    # ========== 研究分析类 (research) ==========
    {"query": "最近有什么新闻", "expected_route": "research", "category": "研究分析", "difficulty": "easy"},
    {"query": "有什么利好利空消息？", "expected_route": "research", "category": "研究分析", "difficulty": "easy"},
    {"query": "和竞争对手比怎么样？", "expected_route": "research", "category": "研究分析", "difficulty": "standard"},
    {"query": "行业前景怎么看？", "expected_route": "research", "category": "研究分析", "difficulty": "standard"},
    {"query": "美联储降息对这只股票有什么影响？", "expected_route": "research", "category": "研究分析", "difficulty": "hard"},
    {"query": "管理层最近有什么变动？", "expected_route": "research", "category": "研究分析", "difficulty": "standard"},
    {"query": "护城河是什么？", "expected_route": "research", "category": "研究分析", "difficulty": "hard"},
    {"query": "机构持仓有什么变化？", "expected_route": "research", "category": "研究分析", "difficulty": "standard"},
    {"query": "什么时候发布财报？", "expected_route": "research", "category": "研究分析", "difficulty": "easy"},

    # ========== 投资建议类 (advisor_only) ==========
    {"query": "现在能买吗", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "easy"},
    {"query": "现在适合买入吗，还是再等等？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "standard"},
    {"query": "如果已经亏损20%，应该止损还是补仓？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "hard"},
    {"query": "这只股票占我仓位的50%，风险大吗？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "standard"},
    {"query": "目标价应该是多少？止损位设在哪里？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "hard"},
    {"query": "我的投资期限是3年，适合投资这只股票吗？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "standard"},
    {"query": "能总结一下这只股票的投资亮点和风险吗？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "standard"},
    {"query": "估值已经这么高了，还能涨吗？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "hard"},
    {"query": "考虑到我的保守风险偏好，这只股票合适吗？", "expected_route": "advisor_only", "category": "投资建议", "difficulty": "standard"},

    # ========== 模糊/歧义类 (advisor_only/ambiguous) ==========
    {"query": "这个怎么样？", "expected_route": "advisor_only", "category": "模糊意图", "difficulty": "ambiguous"},
    {"query": "分析一下", "expected_route": "full", "category": "模糊意图", "difficulty": "ambiguous"},
    {"query": "怎么看", "expected_route": "advisor_only", "category": "模糊意图", "difficulty": "ambiguous"},
    {"query": "评价一下", "expected_route": "advisor_only", "category": "模糊意图", "difficulty": "ambiguous"},
    {"query": "说说这个", "expected_route": "advisor_only", "category": "模糊意图", "difficulty": "ambiguous"},

    # ========== 综合分析类 (full) ==========
    {"query": "全面分析一下这只股票", "expected_route": "full", "category": "综合分析", "difficulty": "standard"},
    {"query": "PE高但增长快，怎么选", "expected_route": "full", "category": "综合分析", "difficulty": "hard"},
    {"query": "基本面和技术面怎么看", "expected_route": "full", "category": "综合分析", "difficulty": "hard"},
    {"query": "财务数据、新闻和估值都分析一下", "expected_route": "full", "category": "综合分析", "difficulty": "hard"},

    # ========== 非股票类 (unknown) ==========
    {"query": "今天天气怎么样", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "推荐一部好电影", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "1+1等于几", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "比特币值得投资吗", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "什么是最好的股票", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "推荐一个券商", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
    {"query": "大盘明天涨还是跌", "expected_route": "unknown", "category": "非股票", "difficulty": "easy"},
]


def load_test_cases() -> list[TestCase]:
    """加载测试用例"""
    return [TestCase(**case) for case in EXPANDED_TEST_SET]


async def evaluate_single_case(
    case: TestCase,
    config: ThresholdConfig,
    ticker: str = "AAPL"
) -> dict:
    """评估单个测试用例"""
    start = time.perf_counter()

    try:
        decision: RoutingDecision = await enhanced_route_followup(
            ticker=ticker,
            question=case.query,
            history_summary="",
            enable_rag=True,
            enable_few_shot=True,
            rule_confidence_threshold=config.rule_threshold,
            rag_high_confidence_threshold=config.rag_high_threshold,
            rag_low_confidence_threshold=config.rag_low_threshold,
        )

        latency_ms = (time.perf_counter() - start) * 1000

        # 判断是否使用了LLM
        used_llm = decision.source in ("rag_few_shot_llm", "llm_fallback", "llm")
        is_rag_direct = decision.source in ("rag_direct", "rag_fallback")
        is_rule_direct = decision.source in ("hard_rule", "soft_rule")

        return {
            "query": case.query,
            "expected": case.expected_route,
            "predicted": decision.route,
            "correct": decision.route == case.expected_route,
            "source": decision.source,
            "confidence": decision.confidence,
            "latency_ms": latency_ms,
            "used_llm": used_llm,
            "is_rag_direct": is_rag_direct,
            "is_rule_direct": is_rule_direct,
            "category": case.category,
            "difficulty": case.difficulty,
        }
    except Exception as e:
        return {
            "query": case.query,
            "expected": case.expected_route,
            "predicted": "ERROR",
            "correct": False,
            "source": "error",
            "confidence": 0,
            "latency_ms": 0,
            "used_llm": False,
            "is_rag_direct": False,
            "is_rule_direct": False,
            "category": case.category,
            "difficulty": case.difficulty,
            "error": str(e),
        }


async def evaluate_threshold_config(
    test_cases: list[TestCase],
    config: ThresholdConfig,
) -> EvaluationResult:
    """评估一组阈值配置"""
    results = await asyncio.gather(*[
        evaluate_single_case(case, config)
        for case in test_cases
    ])

    # 统计指标
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    llm_calls = sum(1 for r in results if r["used_llm"])
    rag_direct = sum(1 for r in results if r["is_rag_direct"])
    rule_direct = sum(1 for r in results if r["is_rule_direct"])
    total_latency = sum(r["latency_ms"] for r in results)

    # 成本效率：正确决策中跳过LLM的比例
    correct_results = [r for r in results if r["correct"]]
    if correct_results:
        correct_without_llm = sum(1 for r in correct_results if not r["used_llm"])
        cost_efficiency = correct_without_llm / len(correct_results)
    else:
        cost_efficiency = 0

    accuracy = correct / total if total > 0 else 0
    avg_latency = total_latency / total if total > 0 else 0

    return EvaluationResult(
        config=config,
        total_cases=total,
        correct_predictions=correct,
        llm_calls=llm_calls,
        rag_direct_hits=rag_direct,
        rule_direct_hits=rule_direct,
        total_latency_ms=total_latency,
        accuracy=accuracy,
        cost_efficiency=cost_efficiency,
        avg_latency_ms=avg_latency,
    )


def generate_threshold_configs() -> list[ThresholdConfig]:
    """生成阈值配置组合（网格搜索）"""
    configs = []

    # 规则引擎阈值
    rule_thresholds = [0.6, 0.65, 0.7, 0.75, 0.8]

    # RAG高置信度阈值
    rag_high_thresholds = [0.7, 0.75, 0.8, 0.85]

    # RAG低置信度阈值（必须小于高阈值）
    rag_low_thresholds = [0.4, 0.45, 0.5, 0.55]

    for rule_th in rule_thresholds:
        for rag_high in rag_high_thresholds:
            for rag_low in rag_low_thresholds:
                # 确保低阈值 < 高阈值
                if rag_low < rag_high:
                    configs.append(ThresholdConfig(
                        rule_threshold=rule_th,
                        rag_high_threshold=rag_high,
                        rag_low_threshold=rag_low,
                    ))

    return configs


def find_pareto_optimal(results: list[EvaluationResult]) -> list[EvaluationResult]:
    """找到帕累托最优解集

    帕累托最优：在不降低其他指标的情况下，无法改进任何一个指标
    """
    pareto = []

    for result in results:
        is_dominated = False

        for other in results:
            if other is result:
                continue

            # 检查 other 是否支配 result
            # other 在至少一个指标上更好，且在其他指标上不更差
            better_in_some = (
                other.accuracy > result.accuracy or
                other.cost_efficiency > result.cost_efficiency or
                other.avg_latency_ms < result.avg_latency_ms
            )

            not_worse_in_any = (
                other.accuracy >= result.accuracy and
                other.cost_efficiency >= result.cost_efficiency and
                other.avg_latency_ms <= result.avg_latency_ms
            )

            if better_in_some and not_worse_in_any:
                is_dominated = True
                break

        if not is_dominated:
            pareto.append(result)

    # 按准确率排序
    pareto.sort(key=lambda x: x.accuracy, reverse=True)
    return pareto


def print_results_table(results: list[EvaluationResult], top_n: int = 10):
    """打印结果表格"""
    # 按准确率排序
    sorted_results = sorted(results, key=lambda x: x.accuracy, reverse=True)

    print("\n" + "=" * 120)
    print(f"{'Rank':<6} {'Rule':<6} {'RAG-H':<6} {'RAG-L':<6} {'Accuracy':<10} {'Cost-Eff':<10} {'Avg Lat(ms)':<12} {'LLM Calls':<10}")
    print("=" * 120)

    for i, result in enumerate(sorted_results[:top_n], 1):
        config = result.config
        print(f"{i:<6} "
              f"{config.rule_threshold:<6.2f} "
              f"{config.rag_high_threshold:<6.2f} "
              f"{config.rag_low_threshold:<6.2f} "
              f"{result.accuracy:<10.2%} "
              f"{result.cost_efficiency:<10.2%} "
              f"{result.avg_latency_ms:<12.1f} "
              f"{result.llm_calls}/{result.total_cases}")

    print("=" * 120)


def analyze_by_category(results: list[dict], category: str) -> dict:
    """按类别分析准确率"""
    category_results = [r for r in results if r["category"] == category]
    if not category_results:
        return {"accuracy": 0, "count": 0}

    correct = sum(1 for r in category_results if r["correct"])
    return {
        "accuracy": correct / len(category_results),
        "count": len(category_results),
    }


def analyze_by_difficulty(results: list[dict]) -> dict:
    """按难度分析准确率"""
    difficulties = ["easy", "standard", "hard", "ambiguous"]
    analysis = {}

    for difficulty in difficulties:
        diff_results = [r for r in results if r["difficulty"] == difficulty]
        if diff_results:
            correct = sum(1 for r in diff_results if r["correct"])
            analysis[difficulty] = {
                "accuracy": correct / len(diff_results),
                "count": len(diff_results),
            }

    return analysis


async def main():
    parser = argparse.ArgumentParser(description="阈值调优脚本")
    parser.add_argument("--samples", type=int, default=None, help="测试样本数量（默认全部）")
    parser.add_argument("--output", type=str, default="threshold_results.json", help="输出文件路径")
    parser.add_argument("--top-n", type=int, default=10, help="显示前N个结果")
    parser.add_argument("--quick", action="store_true", help="快速模式（只测试部分阈值组合）")
    args = parser.parse_args()

    print("=" * 80)
    print("阈值调优脚本 - 寻找最优的阈值配置")
    print("=" * 80)

    # 加载测试用例
    test_cases = load_test_cases()
    if args.samples:
        test_cases = test_cases[:args.samples]

    print(f"\n加载了 {len(test_cases)} 个测试用例")
    print(f"类别分布: {len(set(c.category for c in test_cases))} 个类别")
    print(f"难度分布: easy={sum(1 for c in test_cases if c.difficulty=='easy')}, "
          f"standard={sum(1 for c in test_cases if c.difficulty=='standard')}, "
          f"hard={sum(1 for c in test_cases if c.difficulty=='hard')}, "
          f"ambiguous={sum(1 for c in test_cases if c.difficulty=='ambiguous')}")

    # 生成阈值配置
    if args.quick:
        # 快速模式：只测试关键组合
        configs = [
            ThresholdConfig(0.7, 0.75, 0.5),  # 当前默认值
            ThresholdConfig(0.65, 0.7, 0.45),
            ThresholdConfig(0.75, 0.8, 0.55),
            ThresholdConfig(0.6, 0.75, 0.5),
            ThresholdConfig(0.7, 0.8, 0.5),
        ]
    else:
        configs = generate_threshold_configs()

    print(f"\n将测试 {len(configs)} 组阈值配置")
    print("-" * 80)

    # 评估所有配置
    results: list[EvaluationResult] = []

    for i, config in enumerate(configs, 1):
        print(f"\n[{i}/{len(configs)}] 测试配置: "
              f"rule={config.rule_threshold:.2f}, "
              f"rag_high={config.rag_high_threshold:.2f}, "
              f"rag_low={config.rag_low_threshold:.2f}")

        result = await evaluate_threshold_config(test_cases, config)
        results.append(result)

        print(f"  准确率: {result.accuracy:.2%} | "
              f"成本效率: {result.cost_efficiency:.2%} | "
              f"平均延迟: {result.avg_latency_ms:.1f}ms | "
              f"LLM调用: {result.llm_calls}/{result.total_cases}")

    # 打印结果表格
    print_results_table(results, top_n=args.top_n)

    # 找到帕累托最优
    print("\n" + "=" * 80)
    print("帕累托最优解集（多目标优化）:")
    print("=" * 80)
    pareto = find_pareto_optimal(results)
    print_results_table(pareto, top_n=5)

    # 推荐配置
    print("\n" + "=" * 80)
    print("推荐配置:")
    print("=" * 80)

    # 1. 最高准确率
    best_accuracy = max(results, key=lambda x: x.accuracy)
    print(f"\n1. 最高准确率配置:")
    print(f"   阈值: rule={best_accuracy.config.rule_threshold}, "
          f"rag_high={best_accuracy.config.rag_high_threshold}, "
          f"rag_low={best_accuracy.config.rag_low_threshold}")
    print(f"   指标: 准确率={best_accuracy.accuracy:.2%}, "
          f"成本效率={best_accuracy.cost_efficiency:.2%}, "
          f"平均延迟={best_accuracy.avg_latency_ms:.1f}ms")

    # 2. 最佳成本效率（准确率>80%的前提下）
    high_accuracy_results = [r for r in results if r.accuracy >= 0.8]
    if high_accuracy_results:
        best_cost_eff = max(high_accuracy_results, key=lambda x: x.cost_efficiency)
        print(f"\n2. 最佳成本效率配置（准确率≥80%）:")
        print(f"   阈值: rule={best_cost_eff.config.rule_threshold}, "
              f"rag_high={best_cost_eff.config.rag_high_threshold}, "
              f"rag_low={best_cost_eff.config.rag_low_threshold}")
        print(f"   指标: 准确率={best_cost_eff.accuracy:.2%}, "
              f"成本效率={best_cost_eff.cost_efficiency:.2%}, "
              f"平均延迟={best_cost_eff.avg_latency_ms:.1f}ms")

    # 3. 平衡配置（帕累托前沿中准确率>85%且成本效率>50%的）
    balanced_candidates = [
        r for r in pareto
        if r.accuracy >= 0.85 and r.cost_efficiency >= 0.5
    ]
    if balanced_candidates:
        # 选择准确率最高的平衡配置
        balanced = max(balanced_candidates, key=lambda x: x.accuracy)
        print(f"\n3. 平衡配置（准确率≥85%, 成本效率≥50%）:")
        print(f"   阈值: rule={balanced.config.rule_threshold}, "
              f"rag_high={balanced.config.rag_high_threshold}, "
              f"rag_low={balanced.config.rag_low_threshold}")
        print(f"   指标: 准确率={balanced.accuracy:.2%}, "
              f"成本效率={balanced.cost_efficiency:.2%}, "
              f"平均延迟={balanced.avg_latency_ms:.1f}ms")

    # 保存详细结果
    output_data = {
        "summary": {
            "total_configs_tested": len(configs),
            "total_test_cases": len(test_cases),
            "best_accuracy": {
                "rule_threshold": best_accuracy.config.rule_threshold,
                "rag_high_threshold": best_accuracy.config.rag_high_threshold,
                "rag_low_threshold": best_accuracy.config.rag_low_threshold,
                "accuracy": best_accuracy.accuracy,
                "cost_efficiency": best_accuracy.cost_efficiency,
                "avg_latency_ms": best_accuracy.avg_latency_ms,
            },
        },
        "all_results": [
            {
                "config": {
                    "rule_threshold": r.config.rule_threshold,
                    "rag_high_threshold": r.config.rag_high_threshold,
                    "rag_low_threshold": r.config.rag_low_threshold,
                },
                "accuracy": r.accuracy,
                "cost_efficiency": r.cost_efficiency,
                "avg_latency_ms": r.avg_latency_ms,
                "llm_calls": r.llm_calls,
                "correct_predictions": r.correct_predictions,
            }
            for r in results
        ],
        "pareto_optimal": [
            {
                "config": {
                    "rule_threshold": r.config.rule_threshold,
                    "rag_high_threshold": r.config.rag_high_threshold,
                    "rag_low_threshold": r.config.rag_low_threshold,
                },
                "accuracy": r.accuracy,
                "cost_efficiency": r.cost_efficiency,
                "avg_latency_ms": r.avg_latency_ms,
            }
            for r in pareto[:5]
        ],
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n详细结果已保存到: {args.output}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
