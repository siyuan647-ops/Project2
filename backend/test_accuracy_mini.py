"""意图识别准确率测试 - 精简版（6个样本，控制成本）

预估成本：
- 6个样本 × 2种方案 × 平均2次LLM调用 = ~24次LLM调用
- 每次调用约2K Token × ¥0.015/1K = ¥0.03
- 总成本约 ¥0.7
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.routing import route_followup, original_route_followup


# 精选6个测试样本（覆盖6大类别）
TEST_SAMPLES = [
    {"query": "PE是多少？", "expected": "financial", "category": "标准财务"},
    {"query": "最近有什么新闻", "expected": "research", "category": "研究分析"},
    {"query": "现在能买吗", "expected": "advisor_only", "category": "投资建议"},
    {"query": "这个怎么样", "expected": "advisor_only", "category": "模糊意图"},
    {"query": "PE高但增长快，怎么选", "expected": "full", "category": "复杂case"},
    {"query": "今天天气怎么样", "expected": "unknown", "category": "非股票"},
]


async def test_single_query(query: str, expected: str):
    """测试单个查询，对比新旧方案"""

    # 测试增强版
    start = time.perf_counter()
    try:
        decision_enhanced = await route_followup(
            ticker="AAPL",
            question=query,
            history_summary=""
        )
        enhanced_time = (time.perf_counter() - start) * 1000
        result_enhanced = decision_enhanced.route
        source = decision_enhanced.source
        confidence = decision_enhanced.confidence
    except Exception as e:
        result_enhanced = f"ERROR: {str(e)[:30]}"
        source = "error"
        confidence = 0
        enhanced_time = 0

    # 测试原版
    start = time.perf_counter()
    try:
        decision_original = await original_route_followup(
            ticker="AAPL",
            question=query,
            history_summary=""
        )
        original_time = (time.perf_counter() - start) * 1000
        result_original = decision_original.route
    except Exception as e:
        result_original = f"ERROR: {str(e)[:30]}"
        original_time = 0

    return {
        "query": query,
        "expected": expected,
        "enhanced": result_enhanced,
        "original": result_original,
        "enhanced_match": result_enhanced == expected,
        "original_match": result_original == expected,
        "source": source,
        "confidence": confidence,
        "enhanced_time": enhanced_time,
        "original_time": original_time,
    }


async def main():
    """主测试函数"""
    print("=" * 70)
    print("意图识别准确率测试 - 精简版 (6个样本)")
    print("=" * 70)
    print("\n[测试说明]")
    print("- 测试样本: 6个（覆盖6大意图类别）")
    print("- 对比方案: 增强版(五级路由) vs 原版(三级路由)")
    print("- 预估成本: ~0.7元 (约24次LLM调用)")
    print("\n开始测试...\n")

    results = []
    total_start = time.perf_counter()

    for i, sample in enumerate(TEST_SAMPLES, 1):
        print(f"[{i}/6] 测试: \"{sample['query']}\"")
        print(f"      类别: {sample['category']} | 期望: {sample['expected']}")

        result = await test_single_query(sample["query"], sample["expected"])
        results.append(result)

        # 显示结果
        match_e = "PASS" if result["enhanced_match"] else "FAIL"
        match_o = "PASS" if result["original_match"] else "FAIL"

        print(f"      增强版: {result['enhanced']:12} {match_e} (source={result['source']}, conf={result['confidence']:.2f})")
        print(f"      原版:   {result['original']:12} {match_o}")
        print()

    total_time = (time.perf_counter() - total_start)

    # 汇总统计
    print("=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    total = len(results)
    enhanced_correct = sum(1 for r in results if r["enhanced_match"])
    original_correct = sum(1 for r in results if r["original_match"])

    enhanced_acc = enhanced_correct / total * 100
    original_acc = original_correct / total * 100

    print(f"\n总测试数: {total}")
    print(f"\n增强版正确: {enhanced_correct}/{total} ({enhanced_acc:.1f}%)")
    print(f"原版正确:   {original_correct}/{total} ({original_acc:.1f}%)")
    print(f"\n准确率提升: {enhanced_acc - original_acc:+.1f}%")

    # 详细分析
    print("\n" + "-" * 70)
    print("详细分析")
    print("-" * 70)

    # 增强版正确但原版错误
    enhanced_better = [r for r in results if r["enhanced_match"] and not r["original_match"]]
    if enhanced_better:
        print(f"\n[增强版优于原版] ({len(enhanced_better)}个):")
        for r in enhanced_better:
            print(f"  ✓ \"{r['query']}\"")
            print(f"    期望: {r['expected']} | 增强版: {r['enhanced']} | 原版: {r['original']}")

    # 原版正确但增强版错误
    original_better = [r for r in results if not r["enhanced_match"] and r["original_match"]]
    if original_better:
        print(f"\n[原版优于增强版] ({len(original_better)}个):")
        for r in original_better:
            print(f"  ✗ \"{r['query']}\"")
            print(f"    期望: {r['expected']} | 增强版: {r['enhanced']} | 原版: {r['original']}")

    # Source分布
    print("\n[增强版决策路径分布]:")
    source_counts = {}
    for r in results:
        src = r["source"]
        source_counts[src] = source_counts.get(src, 0) + 1
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {src:20}: {count}次 ({pct:.0f}%)")

    # 时间统计
    avg_time_e = sum(r["enhanced_time"] for r in results) / total
    avg_time_o = sum(r["original_time"] for r in results) / total
    print(f"\n[平均响应时间]:")
    print(f"  增强版: {avg_time_e:.0f}ms")
    print(f"  原版:   {avg_time_o:.0f}ms")

    print(f"\n[总耗时]: {total_time:.1f}秒")

    # 简历数据建议
    print("\n" + "=" * 70)
    print("简历数据建议 (基于6个样本测试)")
    print("=" * 70)
    print(f"\n【意图识别优化】")
    print(f"  设计五级混合路由管线，对比测试显示:")
    print(f"  - 意图分类准确率: {original_acc:.0f}% → {enhanced_acc:.0f}% ({enhanced_acc - original_acc:+.0f}%)")
    print(f"  - 平均响应时间: {avg_time_o:.0f}ms → {avg_time_e:.0f}ms")
    print(f"  - 覆盖6大意图类别: 财务指标/研究分析/投资建议/模糊意图/复杂case/非股票")

    return results


if __name__ == "__main__":
    try:
        results = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试出错: {e}")
        import traceback
        traceback.print_exc()
