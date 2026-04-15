"""RAG意图识别测试脚本

测试RAG意图召回的效果，对比原方案和增强方案的路由决策。
"""

import asyncio
import sys
from pathlib import Path

# 添加backend到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.routing.rag_intent_retriever import get_rag_retriever, IntentCase
from app.routing.intent_knowledge_base import INTENT_KNOWLEDGE_CASES
from app.routing import route_followup, original_route_followup
from app.routing.types import RoutingDecision


# 测试用例 - 覆盖不同意图类型
def get_test_queries():
    """获取测试查询"""
    return [
        # 标准财务指标
        {"query": "PE是多少？", "expected": "financial"},
        {"query": "这个公司的ROE怎么样", "expected": "financial"},
        {"query": "现金流情况如何", "expected": "financial"},

        # 研究分析
        {"query": "最近有什么新闻", "expected": "research"},
        {"query": "和竞争对手比怎么样", "expected": "research"},
        {"query": "机构持仓有变化吗", "expected": "research"},

        # 投资建议
        {"query": "现在能买吗", "expected": "advisor_only"},
        {"query": "亏了20%怎么办", "expected": "advisor_only"},
        {"query": "目标价多少", "expected": "advisor_only"},

        # 模糊意图
        {"query": "这个怎么样", "expected": "advisor_only"},  # 应该需要澄清
        {"query": "分析一下", "expected": "full"},
        {"query": "怎么看", "expected": "advisor_only"},

        # 边界/复杂case
        {"query": "PE高但增长快，怎么选", "expected": "full"},
        {"query": "和之前那只比哪个好", "expected": "advisor_only"},

        # 非股票相关
        {"query": "今天天气怎么样", "expected": "unknown"},
        {"query": "帮我算复利", "expected": "unknown"},

        # 长尾/表述不清
        {"query": "这家公司会不会破产", "expected": "financial"},
        {"query": "大股东在减持", "expected": "research"},
        {"query": "股息率怎么样", "expected": "financial"},
    ]


async def test_rag_retrieval():
    """测试RAG意图召回"""
    print("=" * 60)
    print("测试1: RAG意图召回")
    print("=" * 60)

    retriever = get_rag_retriever()
    test_queries = ["PE是多少？", "这个怎么样", "最近有什么新闻", "现在能买吗"]

    for query in test_queries:
        print(f"\n查询: \"{query}\"")
        print("-" * 40)

        cases = await retriever.retrieve_similar_intents(
            query=query,
            top_k=3,
            similarity_threshold=0.3,
            diversify=True
        )

        if not cases:
            print("  未召回任何案例")
            continue

        for i, case in enumerate(cases, 1):
            print(f"  {i}. [{case.intent_category}] \"{case.query}\" (相似度: {case.similarity:.3f})")
            print(f"     → 路由: {case.route} | 策略: {case.handling_strategy[:30]}...")


async def test_intent_classification():
    """测试意图分类对比"""
    print("\n" + "=" * 60)
    print("测试2: 意图分类对比 (增强版 vs 原版)")
    print("=" * 60)

    test_cases = get_test_queries()

    results = []
    for tc in test_cases:
        query = tc["query"]
        expected = tc["expected"]

        print(f"\n查询: \"{query}\"")
        print(f"期望: {expected}")

        # 测试增强版
        try:
            decision_enhanced = await route_followup(
                ticker="AAPL",
                question=query,
                history_summary=""
            )
            result_enhanced = decision_enhanced.route
            source = decision_enhanced.source
            confidence = decision_enhanced.confidence
        except Exception as e:
            result_enhanced = f"ERROR: {e}"
            source = "error"
            confidence = 0

        # 测试原版
        try:
            decision_original = await original_route_followup(
                ticker="AAPL",
                question=query,
                history_summary=""
            )
            result_original = decision_original.route
        except Exception as e:
            result_original = f"ERROR: {e}"

        # 判断是否匹配期望
        match_enhanced = "✓" if result_enhanced == expected else "✗"
        match_original = "✓" if result_original == expected else "✗"

        print(f"  增强版: {result_enhanced:15} {match_enhanced} (source={source}, conf={confidence:.2f})")
        print(f"  原版:   {result_original:15} {match_original}")

        results.append({
            "query": query,
            "expected": expected,
            "enhanced": result_enhanced,
            "original": result_original,
            "enhanced_match": result_enhanced == expected,
            "original_match": result_original == expected,
        })

    # 汇总统计
    print("\n" + "=" * 60)
    print("汇总统计")
    print("=" * 60)

    total = len(results)
    enhanced_correct = sum(1 for r in results if r["enhanced_match"])
    original_correct = sum(1 for r in results if r["original_match"])

    print(f"总测试数: {total}")
    print(f"增强版正确: {enhanced_correct}/{total} ({enhanced_correct/total*100:.1f}%)")
    print(f"原版正确:   {original_correct}/{total} ({original_correct/total*100:.1f}%)")

    # 显示差异
    print("\n差异分析 (增强版正确但原版错误):")
    for r in results:
        if r["enhanced_match"] and not r["original_match"]:
            print(f"  ✓ \"{r['query']}\" → 增强版: {r['enhanced']}, 原版: {r['original']}")

    print("\n差异分析 (原版正确但增强版错误):")
    for r in results:
        if not r["enhanced_match"] and r["original_match"]:
            print(f"  ✗ \"{r['query']}\" → 增强版: {r['enhanced']}, 原版: {r['original']}")


async def test_knowledge_base_coverage():
    """测试知识库覆盖情况"""
    print("\n" + "=" * 60)
    print("测试3: 意图知识库覆盖情况")
    print("=" * 60)

    from collections import Counter

    categories = Counter(case["intent_category"] for case in INTENT_KNOWLEDGE_CASES)
    routes = Counter(case["route"] for case in INTENT_KNOWLEDGE_CASES)
    difficulties = Counter(case["difficulty"] for case in INTENT_KNOWLEDGE_CASES)

    print(f"\n总案例数: {len(INTENT_KNOWLEDGE_CASES)}")

    print("\n按意图类别分布:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:25}: {count:2} 条")

    print("\n按路由分布:")
    for route, count in sorted(routes.items()):
        print(f"  {route:15}: {count:2} 条")

    print("\n按难度分布:")
    for diff, count in sorted(difficulties.items()):
        print(f"  {diff:15}: {count:2} 条")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("RAG意图识别增强测试")
    print("=" * 60)

    # 测试1: RAG召回
    await test_rag_retrieval()

    # 测试2: 知识库覆盖
    await test_knowledge_base_coverage()

    # 测试3: 意图分类 (需要LLM，可选)
    print("\n" + "=" * 60)
    print("注意: 测试2需要LLM调用，可能需要较长时间")
    print("按 Ctrl+C 跳过，或等待10秒自动开始...")
    print("=" * 60)

    try:
        await asyncio.wait_for(asyncio.sleep(10), timeout=10)
    except asyncio.TimeoutError:
        pass
    except KeyboardInterrupt:
        print("\n跳过意图分类测试")
        return

    await test_intent_classification()


if __name__ == "__main__":
    asyncio.run(main())
