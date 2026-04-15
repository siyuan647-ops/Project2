"""Parallel analysis – runs Research and Financial analysts concurrently.

This module provides a faster initial analysis by running the Research Analyst
and Financial Analyst in parallel, then passing both results to the Investment
Advisor for synthesis.
"""

from __future__ import annotations

import logging

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage, ToolCallSummaryMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from app.agents.llm_config import get_model_client
from app.agents.research_analyst import create_research_analyst
from app.agents.financial_analyst import create_financial_analyst
from app.agents.investment_advisor import create_investment_advisor

logger = logging.getLogger(__name__)


def _extract_content(message) -> str:
    """Extract text content from a message."""
    if isinstance(message, (TextMessage, ToolCallSummaryMessage)):
        return message.content
    if hasattr(message, "content") and isinstance(message.content, str):
        return message.content
    return ""


async def _run_research_analysis(ticker: str, conversation_id: str | None = None, log_trace=None) -> str:
    """Run Research Analyst and return the analysis text."""
    agent = create_research_analyst()
    termination = (
        TextMentionTermination("RESEARCH ANALYSIS COMPLETE", sources=["Research_Analyst"])
        | MaxMessageTermination(10)
    )

    team = RoundRobinGroupChat(
        participants=[agent],
        termination_condition=termination,
    )

    task = (
        f"Conduct comprehensive research analysis for {ticker}.\n\n"
        f"1. Use get_stock_info('{ticker}') to get company fundamentals\n"
        f"2. Use search_company_news to find recent news about {ticker}\n"
        f"3. Analyze the company, industry trends, competitive landscape, risks and opportunities\n"
        f"4. Provide your findings in a structured format\n\n"
        f"Remember to state 'RESEARCH ANALYSIS COMPLETE' when finished."
    )

    if log_trace:
        await log_trace("Research_Analyst", "task_start", task)

    result = await team.run(task=task)

    # Log all messages in the conversation
    if log_trace:
        for i, msg in enumerate(result.messages):
            content = _extract_content(msg)
            msg_type = type(msg).__name__
            await log_trace(
                "Research_Analyst",
                f"message_{i}_{msg_type}",
                content[:2000] if content else f"[{msg_type}]",
                {"source": getattr(msg, "source", "unknown"), "type": msg_type}
            )

    # Extract the final content
    for message in reversed(result.messages):
        content = _extract_content(message)
        if content and message.source == "Research_Analyst":
            return content
    return "Research analysis completed."


async def _run_financial_analysis(ticker: str, conversation_id: str | None = None, log_trace=None) -> str:
    """Run Financial Analyst and return the analysis text."""
    agent = create_financial_analyst()
    termination = (
        TextMentionTermination("FINANCIAL ANALYSIS COMPLETE", sources=["Financial_Analyst"])
        | MaxMessageTermination(10)
    )

    team = RoundRobinGroupChat(
        participants=[agent],
        termination_condition=termination,
    )

    task = (
        f"Conduct comprehensive financial analysis for {ticker}.\n\n"
        f"1. Use get_financial_statements('{ticker}') to get financial data\n"
        f"2. Use get_price_history('{ticker}') to get price trends\n"
        f"3. Analyze profitability, balance sheet health, cash flow, and valuation\n"
        f"4. Provide your findings in a structured format\n\n"
        f"Remember to state 'FINANCIAL ANALYSIS COMPLETE' when finished."
    )

    if log_trace:
        await log_trace("Financial_Analyst", "task_start", task)

    result = await team.run(task=task)

    # Log all messages in the conversation
    if log_trace:
        for i, msg in enumerate(result.messages):
            content = _extract_content(msg)
            msg_type = type(msg).__name__
            await log_trace(
                "Financial_Analyst",
                f"message_{i}_{msg_type}",
                content[:2000] if content else f"[{msg_type}]",
                {"source": getattr(msg, "source", "unknown"), "type": msg_type}
            )

    # Extract the final content
    for message in reversed(result.messages):
        content = _extract_content(message)
        if content and message.source == "Financial_Analyst":
            return content
    return "Financial analysis completed."


async def _run_investment_synthesis(
    ticker: str,
    research_analysis: str,
    financial_analysis: str,
    conversation_id: str | None = None,
    log_trace=None,
) -> str:
    """Run Investment Advisor to synthesize both analyses into a final report."""
    advisor = create_investment_advisor()
    termination = (
        TextMentionTermination(
            "INVESTMENT ADVISORY REPORT COMPLETE",
            sources=["Investment_Advisor"],
        )
        | MaxMessageTermination(5)
    )

    team = RoundRobinGroupChat(
        participants=[advisor],
        termination_condition=termination,
    )

    task = (
        f"Synthesize the following analyses for **{ticker}** into a comprehensive investment report.\n\n"
        f"## RULES for Factual Data (事实数据必须遵守)\n"
        f"以下必须使用下方分析中的具体数据，严禁编造：\n"
        f"- 股价、PE/PB、市值等财务指标\n"
        f"- 营收、利润、现金流等财报数据\n"
        f"- 具体新闻事件、公司信息\n"
        f"\n"
        f"## 允许的专业知识\n"
        f"你可以使用专业知识进行：投资框架应用、行业趋势分析、风险评估、策略建议\n\n"
        f"## Research Analysis (数据来源：Research Analyst)\n"
        f"{research_analysis}\n\n"
        f"## Financial Analysis (数据来源：Financial Analyst)\n"
        f"{financial_analysis}\n\n"
        f"---\n\n"
        f"Based on the above analyses, create a strategic investment plan for {ticker}.\n\n"
        f"Format the output in Markdown with clear sections for:\n"
        f"- 'Executive Summary (执行摘要)'\n"
        f"- 'Key Risks (主要风险)'\n"
        f"- 'Final Recommendation (最终投资建议)'\n\n"
        f"CRITICAL: Always translate and respond in fluent Professional Chinese. "
        f"Use EXACT numbers from the analyses above. "
        f"Provide a detailed and comprehensive report with specific data and analysis.\n\n"
        f"End your report with \"INVESTMENT ADVISORY REPORT COMPLETE\"."
    )

    if log_trace:
        await log_trace("Investment_Advisor", "task_start", f"Synthesizing research and financial analysis for {ticker}", {
            "research_length": len(research_analysis),
            "financial_length": len(financial_analysis)
        })

    result = await team.run(task=task)

    # Log all messages in the conversation
    if log_trace:
        for i, msg in enumerate(result.messages):
            content = _extract_content(msg)
            msg_type = type(msg).__name__
            await log_trace(
                "Investment_Advisor",
                f"message_{i}_{msg_type}",
                content[:2000] if content else f"[{msg_type}]",
                {"source": getattr(msg, "source", "unknown"), "type": msg_type}
            )

    # Extract the final content
    for message in reversed(result.messages):
        content = _extract_content(message)
        if content and message.source == "Investment_Advisor":
            return content
    return "Investment analysis completed."


async def run_parallel_analysis(ticker: str, conversation_id: str | None = None) -> str:
    """
    Run the full three-agent analysis for *ticker* with parallel execution.

    Research Analyst and Financial Analyst run concurrently.
    Investment Advisor runs after both complete to synthesize the results.

    Returns the final investment advisory report.
    """
    from app.storage import store

    logger.info(f"Starting parallel analysis for {ticker}")

    async def log_trace(agent_name: str, trace_type: str, content: str, metadata: dict = None):
        """Helper to log agent traces."""
        if conversation_id:
            try:
                await store.log_agent_trace(
                    conversation_id=conversation_id,
                    turn=1,
                    agent_name=agent_name,
                    trace_type=trace_type,
                    content=content,
                    metadata=metadata,
                )
            except Exception as e:
                logger.warning(f"Failed to log agent trace: {e}")

    # Phase 1: Run Research and Financial analysts in parallel
    logger.info(f"[{ticker}] Phase 1/3: Running Research and Financial analysts in parallel...")
    await log_trace("System", "phase_start", "Starting parallel analysis: Research and Financial analysts")

    import asyncio

    research_task = _run_research_analysis(ticker, conversation_id, log_trace)
    financial_task = _run_financial_analysis(ticker, conversation_id, log_trace)

    research_result, financial_result = await asyncio.gather(
        research_task, financial_task, return_exceptions=True
    )

    # Handle exceptions
    if isinstance(research_result, Exception):
        logger.error(f"Research analysis failed: {research_result}")
        await log_trace("Research_Analyst", "error", str(research_result))
        research_result = f"Research analysis encountered an error: {research_result}"
    else:
        await log_trace("Research_Analyst", "output", research_result[:2000] + "..." if len(research_result) > 2000 else research_result)

    if isinstance(financial_result, Exception):
        logger.error(f"Financial analysis failed: {financial_result}")
        await log_trace("Financial_Analyst", "error", str(financial_result))
        financial_result = f"Financial analysis encountered an error: {financial_result}"
    else:
        await log_trace("Financial_Analyst", "output", financial_result[:2000] + "..." if len(financial_result) > 2000 else financial_result)

    logger.info(f"[{ticker}] Phase 1 complete: Research={len(research_result)} chars, Financial={len(financial_result)} chars")
    await log_trace("System", "phase_complete", f"Phase 1 complete. Research: {len(research_result)} chars, Financial: {len(financial_result)} chars")

    # Phase 2: Run Investment Advisor to synthesize results
    logger.info(f"[{ticker}] Phase 2/3: Running Investment Advisor synthesis...")
    await log_trace("System", "phase_start", "Starting Investment Advisor synthesis")

    report = await _run_investment_synthesis(ticker, research_result, financial_result, conversation_id, log_trace)

    logger.info(f"[{ticker}] Phase 3/3: Analysis complete. Report length: {len(report)} chars")
    await log_trace("Investment_Advisor", "output", report[:3000] + "..." if len(report) > 3000 else report)
    await log_trace("System", "analysis_complete", f"Analysis complete. Report length: {len(report)} chars")

    return report
