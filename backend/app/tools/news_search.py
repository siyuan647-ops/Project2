"""Web search for company news using Tavily (primary) and DuckDuckGo (fallback)."""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from app.tools.tool_logger import logged_tool

if TYPE_CHECKING:
    from tavily import TavilyClient

logger = logging.getLogger(__name__)

# Trusted financial news domains for Tavily search
TRUSTED_NEWS_DOMAINS = [
    "bloomberg.com",
    "reuters.com",
    "cnbc.com",
    "wsj.com",
    "ft.com",
    "marketwatch.com",
    "seekingalpha.com",
    "investopedia.com",
    "finance.yahoo.com",
    "morningstar.com",
    "thestreet.com",
    "zacks.com",
    "fool.com",
    "benzinga.com",
    "economist.com",
    "forbes.com",
    "businessinsider.com",
    "techcrunch.com",
    "theverge.com",
]


def _search_tavily(company_name: str, num_results: int = 8) -> str | None:
    """Search using Tavily API. Returns None if API key missing or error occurs."""
    from app.config import settings

    if not settings.TAVILY_API_KEY:
        logger.debug("TAVILY_API_KEY not configured, skipping Tavily search")
        return None

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)

        # Build search query focused on financial news
        query = f"{company_name} stock company news recent financial earnings"

        response = client.search(
            query=query,
            search_depth="advanced",
            time_range="week",
            max_results=num_results,
            include_domains=TRUSTED_NEWS_DOMAINS,
            include_answer=True,  # Get AI-generated summary
        )

        results = response.get("results", [])
        if not results:
            return None

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            # Tavily provides 'content' which is already summarized/extracted
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            published_date = r.get("published_date", "Recent")

            lines.append(
                f"{i}. **{title}** ({published_date})\n   {content}\n   Link: {url}"
            )

        # Add Tavily's AI answer as a summary if available
        answer = response.get("answer", "")
        if answer:
            header = f"**AI Summary**: {answer}\n\n---\n\n"
            return header + "\n\n".join(lines)

        return "\n\n".join(lines)

    except Exception as e:
        logger.warning(f"Tavily search failed: {e}, will fallback to DuckDuckGo")
        return None


def _search_duckduckgo(company_name: str, num_results: int = 8) -> str:
    """Fallback search using DuckDuckGo (original implementation)."""
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.news(company_name, max_results=num_results))

    if not results:
        return f"No recent news found for '{company_name}'."

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        body = r.get("body", "")[:200]
        source = r.get("source", "")
        date = r.get("date", "")
        url = r.get("url", "")
        lines.append(f"{i}. **{title}** ({source}, {date})\n   {body}\n   Link: {url}")

    return "\n\n".join(lines)


@logged_tool("search_company_news")
async def search_company_news(company_name: str, num_results: int = 8) -> str:
    """Search for recent news about *company_name* and return formatted results.

    Uses Tavily API as primary search (if configured), falls back to DuckDuckGo.
    """
    # Try Tavily first
    tavily_result = _search_tavily(company_name, num_results)
    if tavily_result:
        return tavily_result

    # Fallback to DuckDuckGo
    logger.info(f"Falling back to DuckDuckGo for news search: {company_name}")
    return _search_duckduckgo(company_name, num_results)
