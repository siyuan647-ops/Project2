"""系统综合评估脚本

一键运行所有测试，生成评估报告
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from app.routing import enhanced_route_followup
from app.agents.group_chat import run_followup
from app.storage import store


@dataclass
class TestResult:
    """测试结果"""
    test_name: str
    passed: bool
    score: float  # 0-100
    details: dict
    duration_ms: float


class SystemEvaluator:
    """系统评估器"""

    def __init__(self):
        self.results: list[TestResult] = []

    async def run_all_tests(self):
        """运行所有测试套件"""
        print("=" * 80)
        print("系统综合评估")
        print("=" * 80)

        # 1. 路由准确性测试
        await self.test_routing_accuracy()

        # 2. 延迟性能测试
        await self.test_latency()

        # 3. 成本效率测试
        await self.test_cost_efficiency()

        # 4. 鲁棒性测试
        await self.test_robustness()

        # 生成报告
        self.generate_report()

    async def test_routing_accuracy(self):
        """测试路由准确性"""
        print("\n📊 测试1: 路由准确性")

        test_cases = [
            {"query": "PE是多少？", "expected": "financial", "weight": 1.0},
            {"query": "最近有什么新闻", "expected": "research", "weight": 1.0},
            {"query": "现在能买吗", "expected": "advisor_only", "weight": 1.0},
            {"query": "全面分析一下", "expected": "full", "weight": 1.0},
            {"query": "今天天气", "expected": "unknown", "weight": 1.0},
            {"query": "ROE为什么下降了", "expected": "financial", "weight": 1.2},  # 更难
            {"query": "这个怎么样", "expected": "advisor_only", "weight": 1.5},    # 模糊
        ]

        correct = 0
        total_weight = 0

        for case in test_cases:
            try:
                decision = await enhanced_route_followup(
                    ticker="AAPL",
                    question=case["query"],
                    history_summary=""
                )
                if decision.route == case["expected"]:
                    correct += case["weight"]
                total_weight += case["weight"]
            except Exception as e:
                print(f"  ❌ {case['query']}: {e}")

        accuracy = (correct / total_weight) * 100 if total_weight > 0 else 0

        result = TestResult(
            test_name="路由准确性",
            passed=accuracy >= 80,
            score=accuracy,
            details={"tested": len(test_cases), "weighted_correct": correct},
            duration_ms=0
        )
        self.results.append(result)
        print(f"  加权准确率: {accuracy:.1f}% {'✅' if accuracy >= 80 else '❌'}")

    async def test_latency(self):
        """测试延迟性能"""
        print("\n⏱️  测试2: 延迟性能")

        # 测试路由延迟
        latencies = []
        for _ in range(10):
            start = time.time()
            await enhanced_route_followup("AAPL", "PE是多少？")
            latencies.append((time.time() - start) * 1000)

        p50 = sorted(latencies)[len(latencies)//2]
        p95 = sorted(latencies)[int(len(latencies)*0.95)]

        passed = p50 < 200 and p95 < 500
        score = max(0, 100 - (p50 - 100) / 10)  # 100ms基准，每多10ms扣1分

        result = TestResult(
            test_name="延迟性能",
            passed=passed,
            score=score,
            details={"p50_ms": p50, "p95_ms": p95},
            duration_ms=sum(latencies)
        )
        self.results.append(result)
        print(f"  P50: {p50:.1f}ms, P95: {p95:.1f}ms {'✅' if passed else '❌'}")

    async def test_cost_efficiency(self):
        """测试成本效率"""
        print("\n💰 测试3: 成本效率")

        queries = [
            "今天天气", "PE是多少", "现在能买吗", "有什么新闻",
            "分析一下", "ROE怎么样", "目标价多少", "风险大吗"
        ]

        llm_calls = 0
        source_counts = {}

        for query in queries:
            decision = await enhanced_route_followup("AAPL", query)
            source_counts[decision.source] = source_counts.get(decision.source, 0) + 1
            if decision.source in ("rag_few_shot_llm", "llm_fallback", "llm"):
                llm_calls += 1

        skip_rate = (len(queries) - llm_calls) / len(queries) * 100
        passed = skip_rate >= 50

        result = TestResult(
            test_name="成本效率",
            passed=passed,
            score=skip_rate,
            details={"llm_skip_rate": skip_rate, "source_breakdown": source_counts},
            duration_ms=0
        )
        self.results.append(result)
        print(f"  LLM跳过率: {skip_rate:.1f}% {'✅' if passed else '❌'}")
        print(f"  来源分布: {source_counts}")

    async def test_robustness(self):
        """测试鲁棒性"""
        print("\n🛡️  测试4: 鲁棒性")

        edge_cases = [
            {"query": "", "name": "空输入"},
            {"query": "a" * 1000, "name": "超长输入"},
            {"query": "👍🚀💰", "name": "表情符号"},
            {"query": "这个", "name": "极简模糊"},
        ]

        passed = 0
        for case in edge_cases:
            try:
                result = await enhanced_route_followup("AAPL", case["query"])
                # 只要能返回结果（不崩溃）就算通过
                passed += 1
            except Exception as e:
                print(f"  ⚠️  {case['name']}: {e}")

        pass_rate = passed / len(edge_cases) * 100

        result = TestResult(
            test_name="鲁棒性",
            passed=pass_rate >= 80,
            score=pass_rate,
            details={"passed": passed, "total": len(edge_cases)},
            duration_ms=0
        )
        self.results.append(result)
        print(f"  边界通过率: {pass_rate:.0f}% {'✅' if pass_rate >= 80 else '❌'}")

    def generate_report(self):
        """生成评估报告"""
        print("\n" + "=" * 80)
        print("评估报告")
        print("=" * 80)

        total_score = sum(r.score for r in self.results) / len(self.results)
        all_passed = all(r.passed for r in self.results)

        print(f"\n综合得分: {total_score:.1f}/100")
        print(f"整体状态: {'✅ 通过' if all_passed else '❌ 未通过'}")

        print("\n详细结果:")
        for r in self.results:
            status = "✅" if r.passed else "❌"
            print(f"  {status} {r.test_name}: {r.score:.1f}分")

        # 生成JSON报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": total_score,
            "passed": all_passed,
            "tests": [
                {
                    "name": r.test_name,
                    "score": r.score,
                    "passed": r.passed,
                    "details": r.details
                }
                for r in self.results
            ]
        }

        with open("evaluation_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n报告已保存: evaluation_report.json")


async def main():
    evaluator = SystemEvaluator()
    await evaluator.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
