"""验证RAG意图识别系统设置

运行此脚本确保所有新模块可以正确导入和初始化。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """测试所有模块导入"""
    print("=" * 60)
    print("测试模块导入")
    print("=" * 60)

    tests = [
        ("意图知识库", "app.routing.intent_knowledge_base"),
        ("RAG召回器", "app.routing.rag_intent_retriever"),
        ("Prompt构建器", "app.routing.intent_prompt_builder"),
        ("增强路由", "app.routing.enhanced_router"),
        ("类型定义", "app.routing.types"),
    ]

    all_passed = True
    for name, module_path in tests:
        try:
            __import__(module_path)
            print(f"✓ {name:20} - {module_path}")
        except Exception as e:
            print(f"✗ {name:20} - {module_path}")
            print(f"  错误: {e}")
            all_passed = False

    return all_passed


def test_intent_knowledge_base():
    """测试意图知识库"""
    print("\n" + "=" * 60)
    print("测试意图知识库")
    print("=" * 60)

    try:
        from app.routing.intent_knowledge_base import (
            INTENT_KNOWLEDGE_CASES,
            get_cases_by_category,
            get_cases_by_route,
        )

        print(f"✓ 知识库案例总数: {len(INTENT_KNOWLEDGE_CASES)}")

        # 测试分类查询
        financial_cases = get_cases_by_category("financial_metrics")
        print(f"✓ financial_metrics 类别案例数: {len(financial_cases)}")

        research_cases = get_cases_by_route("research")
        print(f"✓ research 路由案例数: {len(research_cases)}")

        # 显示类别分布
        from collections import Counter
        categories = Counter(case["intent_category"] for case in INTENT_KNOWLEDGE_CASES)
        print("\n类别分布:")
        for cat, count in sorted(categories.items()):
            print(f"  - {cat}: {count}")

        return True

    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_retriever_init():
    """测试RAG召回器初始化"""
    print("\n" + "=" * 60)
    print("测试RAG召回器初始化")
    print("=" * 60)

    try:
        from app.routing.rag_intent_retriever import RAGIntentRetriever

        # 创建实例（此时不加载模型）
        retriever = RAGIntentRetriever(use_memory_mode=True)

        # 检查内存索引
        if retriever._memory_cases:
            print(f"✓ 内存案例数: {len(retriever._memory_cases)}")
        else:
            print("⚠ 内存案例未加载（模型可能未初始化）")

        return True

    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_enhanced_router_import():
    """测试增强路由导入"""
    print("\n" + "=" * 60)
    print("测试增强路由导入")
    print("=" * 60)

    try:
        from app.routing import route_followup, original_route_followup, RoutingDecision

        print("✓ route_followup 导入成功 (增强版)")
        print("✓ original_route_followup 导入成功 (原版)")
        print("✓ RoutingDecision 导入成功")

        # 检查函数签名
        import inspect
        sig = inspect.signature(route_followup)
        print(f"\n增强版路由参数: {list(sig.parameters.keys())}")

        return True

    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主验证函数"""
    print("\n" + "=" * 60)
    print("RAG意图识别系统 - 设置验证")
    print("=" * 60)

    results = []

    results.append(("模块导入", test_imports()))
    results.append(("意图知识库", test_intent_knowledge_base()))
    results.append(("RAG召回器", test_rag_retriever_init()))
    results.append(("增强路由", test_enhanced_router_import()))

    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name:20} {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✓ 所有验证通过！RAG意图识别系统已就绪。")
        print("\n下一步:")
        print("  1. 运行测试: python test_rag_intent.py")
        print("  2. 重启后端服务使用新路由")
    else:
        print("\n✗ 部分验证失败，请检查错误信息。")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
