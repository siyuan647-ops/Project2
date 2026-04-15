"""路由准确率评估脚本

使用 intent_knowledge_base.py 中的标注案例评估路由器的准确性。

用法:
    cd backend
    python scripts/evaluate_router.py

输出:
    - 总体准确率
    - 各 route 的准确率
    - 混淆矩阵
    - 错误案例分析
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# 添加项目根目录到路径
sys.path.insert(0, "d:\\project2\\backend")

from app.routing.intent_knowledge_base import INTENT_KNOWLEDGE_CASES
from app.routing.enhanced_router import route_followup
from app.routing.types import Route


@dataclass
class EvaluationResult:
    """单个案例的评估结果"""
    query: str
    expected_route: Route
    predicted_route: Route
    confidence: float
    latency_ms: float
    source: str  # 路由决策来源: hard_rule, soft_rule, rag_direct, rag_few_shot_llm, llm_fallback, fallback
    match: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationReport:
    """评估报告"""
    total: int
    correct: int
    accuracy: float
    avg_latency_ms: float
    avg_confidence: float
    by_route: dict[str, dict[str, Any]]
    by_source: dict[str, dict[str, Any]]
    errors: list[EvaluationResult]


async def evaluate_router() -> EvaluationReport:
    """评估路由器在所有标注案例上的表现"""
    results: list[EvaluationResult] = []

    print(f"开始评估 {len(INTENT_KNOWLEDGE_CASES)} 个标注案例...")
    print("-" * 60)

    for i, case in enumerate(INTENT_KNOWLEDGE_CASES, 1):
        query = case["query"]
        expected_route = case["route"]
        ticker = case.get("extracted_entities", {}).get("ticker", "AAPL")

        print(f"[{i}/{len(INTENT_KNOWLEDGE_CASES)}] 测试: {query[:40]}...")

        import time
        start_time = time.time()

        try:
            decision = await route_followup(
                ticker=ticker,
                question=query,
                history_summary="",
            )

            latency_ms = (time.time() - start_time) * 1000

            result = EvaluationResult(
                query=query,
                expected_route=expected_route,
                predicted_route=decision.route,
                confidence=decision.confidence,
                latency_ms=latency_ms,
                source=decision.source,
                match=decision.route == expected_route,
                metadata=decision.metadata or {},
            )
            results.append(result)

            status = "OK" if result.match else "FAIL"
            print(f"    [{status}] 预期: {expected_route:15s} 实际: {decision.route:15s} "
                  f"置信度: {decision.confidence:.2f} 来源: {decision.source}")

        except Exception as e:
            print(f"    [ERROR] 错误: {e}")
            results.append(EvaluationResult(
                query=query,
                expected_route=expected_route,
                predicted_route="error",
                confidence=0.0,
                latency_ms=0.0,
                source="error",
                match=False,
                metadata={"error": str(e)},
            ))

    # 计算总体指标
    total = len(results)
    correct = sum(1 for r in results if r.match)
    accuracy = correct / total if total > 0 else 0.0
    avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0.0
    avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0.0

    # 按 route 统计
    by_route: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "total": 0, "correct": 0, "accuracy": 0.0, "samples": []
    })
    for r in results:
        route = r.expected_route
        by_route[route]["total"] += 1
        by_route[route]["samples"].append(r.query[:30])
        if r.match:
            by_route[route]["correct"] += 1
    for route in by_route:
        by_route[route]["accuracy"] = (
            by_route[route]["correct"] / by_route[route]["total"]
            if by_route[route]["total"] > 0 else 0.0
        )

    # 按 source 统计
    by_source: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "total": 0, "correct": 0, "accuracy": 0.0
    })
    for r in results:
        by_source[r.source]["total"] += 1
        if r.match:
            by_source[r.source]["correct"] += 1
    for source in by_source:
        by_source[source]["accuracy"] = (
            by_source[source]["correct"] / by_source[source]["total"]
            if by_source[source]["total"] > 0 else 0.0
        )

    # 错误案例
    errors = [r for r in results if not r.match]

    return EvaluationReport(
        total=total,
        correct=correct,
        accuracy=accuracy,
        avg_latency_ms=avg_latency,
        avg_confidence=avg_confidence,
        by_route=dict(by_route),
        by_source=dict(by_source),
        errors=errors,
    )


def print_confusion_matrix(results: list[EvaluationResult]) -> None:
    """打印混淆矩阵"""
    routes = ["advisor_only", "research", "financial", "full", "unknown"]

    # 初始化混淆矩阵
    matrix: dict[str, dict[str, int]] = {r: {c: 0 for c in routes} for r in routes}

    for r in results:
        if r.predicted_route in routes:
            matrix[r.expected_route][r.predicted_route] += 1

    print("\n" + "=" * 70)
    print("混淆矩阵")
    print("=" * 70)
    print(f"{'预期 \\ 预测':<15}", end="")
    for r in routes:
        print(f"{r[:10]:<12}", end="")
    print()
    print("-" * 70)

    for expected in routes:
        print(f"{expected:<15}", end="")
        for predicted in routes:
            count = matrix[expected][predicted]
            marker = "*" if expected == predicted and count > 0 else ""
            marker = "!" if expected != predicted and count > 0 else marker
            print(f"{count:<10}{marker:<2}", end="")
        print()


def print_report(report: EvaluationReport) -> None:
    """打印评估报告"""
    print("\n" + "=" * 70)
    print("评估报告")
    print("=" * 70)

    print(f"\n【总体指标】")
    print(f"  总样本数: {report.total}")
    print(f"  正确预测: {report.correct}")
    print(f"  准确率:   {report.accuracy:.2%}")
    print(f"  平均延迟: {report.avg_latency_ms:.1f}ms")
    print(f"  平均置信度: {report.avg_confidence:.2f}")

    print(f"\n【按 Route 统计】")
    for route, stats in sorted(report.by_route.items()):
        print(f"  {route:15s}: {stats['correct']}/{stats['total']} "
              f"({stats['accuracy']:.1%})")

    print(f"\n【按决策来源统计】")
    for source, stats in sorted(report.by_source.items()):
        print(f"  {source:20s}: {stats['correct']}/{stats['total']} "
              f"({stats['accuracy']:.1%})")

    if report.errors:
        print(f"\n【错误案例分析 ({len(report.errors)} 个)】")
        for i, err in enumerate(report.errors[:10], 1):  # 只显示前10个
            print(f"\n  {i}. Query: {err.query}")
            print(f"     预期: {err.expected_route}")
            print(f"     实际: {err.predicted_route}")
            print(f"     置信度: {err.confidence:.2f}, 来源: {err.source}")

    print("\n" + "=" * 70)


async def main() -> int:
    """主函数"""
    print("路由器准确率评估工具")
    print("=" * 70)

    try:
        report = await evaluate_router()
        # 重构所有结果用于混淆矩阵
        all_results = []
        for e in report.errors:
            all_results.append(e)
        # 添加正确的结果（从统计反推）
        print_confusion_matrix(all_results)
        print_report(report)

        # 保存详细结果到文件
        output_file = "router_evaluation_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "summary": {
                    "total": report.total,
                    "correct": report.correct,
                    "accuracy": report.accuracy,
                    "avg_latency_ms": report.avg_latency_ms,
                    "avg_confidence": report.avg_confidence,
                },
                "by_route": report.by_route,
                "by_source": report.by_source,
                "errors": [
                    {
                        "query": e.query,
                        "expected": e.expected_route,
                        "predicted": e.predicted_route,
                        "confidence": e.confidence,
                        "source": e.source,
                    }
                    for e in report.errors
                ],
            }, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已保存到: {output_file}")

        return 0 if report.accuracy >= 0.85 else 1  # 85% 准确率阈值

    except Exception as e:
        print(f"\n评估失败: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
