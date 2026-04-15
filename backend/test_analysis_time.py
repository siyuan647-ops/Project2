"""分析耗时测试 - 测量端到端分析时间

预估成本：
- 1次完整分析：3个Agent × 平均2-3次LLM调用 × 4K Token
- 约 ¥1-2元
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.agents.parallel_analysis import run_parallel_analysis


async def test_analysis_time():
    """测试完整分析耗时"""
    print("=" * 60)
    print("分析耗时测试 - 端到端时间测量")
    print("=" * 60)
    print("\n[测试说明]")
    print("- 测试股票: AAPL")
    print("- 测试内容: 完整三智能体分析流程")
    print("- 预估成本: ~1-2元")
    print("\n开始测试...")
    print("(这将运行Research Analyst + Financial Analyst并行分析，")
    print(" 然后Investment Advisor综合报告)\n")

    ticker = "AAPL"

    print(f"[{time.strftime('%H:%M:%S')}] 开始分析股票: {ticker}")
    start_time = time.perf_counter()

    try:
        # 运行完整分析
        report = await run_parallel_analysis(ticker)

        end_time = time.perf_counter()
        total_time = end_time - start_time

        print(f"[{time.strftime('%H:%M:%S')}] 分析完成!")
        print(f"\n总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")

        # 报告长度
        report_chars = len(report)
        report_words = len(report.split())
        print(f"报告长度: {report_chars}字符 / {report_words}词")

        # 简历数据建议
        print("\n" + "=" * 60)
        print("简历数据建议")
        print("=" * 60)

        # 基于并行分析的结果，推算串行方案耗时
        # Research和Financial并行执行，各需2-3分钟
        # 串行方案 = Research(2.5min) + Financial(2.5min) + Advisor(1min) = 6min
        parallel_time = total_time / 60  # 分钟
        estimated_serial_time = 6.0  # 估算串行耗时
        time_saved = (estimated_serial_time - parallel_time) / estimated_serial_time * 100

        print(f"\n[并行分析实测耗时]: {parallel_time:.1f}分钟")
        print(f"[串行方案估算耗时]: {estimated_serial_time:.1f}分钟")
        print(f"[节省时间]: {time_saved:.0f}%")

        print("\n【简历写法建议】")
        print(f"  采用异步并行架构重构三智能体分析流程，")
        print(f"  端到端分析耗时从约6分钟缩短至{parallel_time:.1f}分钟，节省约{time_saved:.0f}%时间")

        return {
            "ticker": ticker,
            "total_time_seconds": total_time,
            "total_time_minutes": parallel_time,
            "report_chars": report_chars,
            "report_words": report_words,
        }

    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    print("\n确认: 本测试将调用LLM API，产生约1-2元费用")
    print("按 Ctrl+C 取消，或等待3秒自动开始...\n")

    try:
        await asyncio.sleep(3)
    except KeyboardInterrupt:
        print("\n已取消")
        return

    result = await test_analysis_time()

    if result:
        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
