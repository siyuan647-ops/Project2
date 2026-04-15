"""Stock / financial data: Polygon.io when POLYGON_API_KEY is set, else yfinance."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from app.config import settings
from app.tools.tool_logger import logged_tool

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"

# 简单的内存缓存：已验证的股票代码
_valid_ticker_cache: set[str] = set()
_invalid_ticker_cache: set[str] = set()


def validate_ticker(ticker: str) -> tuple[bool, str | None]:
    """验证股票代码是否有效。

    Returns:
        (is_valid, error_message)
        is_valid: True if valid, False otherwise
        error_message: None if valid, else error description
    """
    import yfinance as yf

    t = ticker.upper().strip()

    # 检查缓存
    if t in _valid_ticker_cache:
        return True, None
    if t in _invalid_ticker_cache:
        return False, f"股票代码 '{ticker}' 不存在或已退市"

    # 方法1: Polygon API (如果配置了)
    if _use_polygon():
        try:
            ref = _polygon_get(f"/v3/reference/tickers/{t}", {})
            results = ref.get("results")
            if results:
                _valid_ticker_cache.add(t)
                return True, None
            else:
                _invalid_ticker_cache.add(t)
                return False, f"Polygon: 找不到股票代码 '{ticker}'，请检查是否为有效的美股代码"
        except RuntimeError as e:
            # Polygon 返回错误，可能是无效代码或API限制
            if "NOT_FOUND" in str(e) or "404" in str(e):
                _invalid_ticker_cache.add(t)
                return False, f"股票代码 '{ticker}' 不存在，请检查拼写"
            # 其他错误（如网络问题），降级到yfinance
            logger.warning(f"Polygon验证失败，降级到yfinance: {e}")

    # 方法2: Yahoo Finance (备用方案)
    try:
        stock = yf.Ticker(t)
        info = stock.info
        # 如果能获取到有效信息，认为代码有效
        if info and (info.get("symbol") or info.get("regularMarketPrice") or info.get("longName")):
            _valid_ticker_cache.add(t)
            return True, None
        else:
            _invalid_ticker_cache.add(t)
            return False, f"Yahoo Finance: 股票代码 '{ticker}' 不存在或无法获取数据"
    except Exception as e:
        logger.warning(f"Yahoo Finance验证失败: {e}")
        _invalid_ticker_cache.add(t)
        return False, f"无法验证股票代码 '{ticker}'，请检查是否为有效代码"


def clear_ticker_cache(ticker: str | None = None):
    """清除股票代码缓存（用于测试或强制刷新）"""
    global _valid_ticker_cache, _invalid_ticker_cache
    if ticker:
        t = ticker.upper().strip()
        _valid_ticker_cache.discard(t)
        _invalid_ticker_cache.discard(t)
    else:
        _valid_ticker_cache.clear()
        _invalid_ticker_cache.clear()


def _use_polygon() -> bool:
    return bool(settings.POLYGON_API_KEY and settings.POLYGON_API_KEY.strip())


def _polygon_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET api.polygon.io with apiKey query param."""
    q: dict[str, Any] = dict(params or {})
    q["apiKey"] = settings.POLYGON_API_KEY.strip()
    url = f"{POLYGON_BASE}{path}?{urlencode(q)}"
    req = Request(url, headers={"User-Agent": "FinancialPlatform/1.0"})
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Polygon HTTP {e.code}: {err_body}") from e
    except URLError as e:
        raise RuntimeError(f"Polygon network error: {e}") from e
    data = json.loads(body)
    err = data.get("error") or data.get("message")
    if isinstance(err, str) and err:
        raise RuntimeError(f"Polygon API error: {err}")
    status = data.get("status")
    if status in ("ERROR", "NOT_FOUND"):
        raise RuntimeError(f"Polygon status={status!r} body={body[:500]}")
    return data


def _polygon_daily_bars(ticker: str, from_d: date, to_d: date) -> list[dict[str, Any]]:
    """Fetch daily aggregates (adjusted)."""
    t = ticker.upper()
    path = f"/v2/aggs/ticker/{t}/range/1/day/{from_d.isoformat()}/{to_d.isoformat()}"
    data = _polygon_get(
        path,
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    return list(data.get("results") or [])


def _get_stock_info_polygon(ticker: str) -> str:
    t = ticker.upper()
    ref = _polygon_get(f"/v3/reference/tickers/{t}", {})
    r = ref.get("results")
    if not r:
        return f"No Polygon reference data for ticker '{ticker}'. Verify US symbol and API tier."

    to_d = date.today()
    from_d = to_d - timedelta(days=400)
    bars = _polygon_daily_bars(t, from_d, to_d)
    last_close = None
    high_52w = low_52w = None
    if bars:
        last_close = bars[-1].get("c")
        high_52w = max(b.get("h") or 0 for b in bars)
        low_52w = min(b.get("l") or float("inf") for b in bars)
        if low_52w == float("inf"):
            low_52w = None

    addr = r.get("address") or {}
    country = "N/A"
    if addr.get("city") or addr.get("state"):
        country = f"{addr.get('state', '')} US".strip()

    fields = {
        "Company": r.get("name", "N/A"),
        "Sector / SIC": r.get("sic_description", "N/A"),
        "Industry (SIC code)": r.get("sic_code", "N/A"),
        "Country / HQ": country,
        "Market Cap": r.get("market_cap", "N/A"),
        "Current Price (last daily close)": last_close if last_close is not None else "N/A",
        "52-Week High (approx from daily bars)": high_52w if high_52w is not None else "N/A",
        "52-Week Low (approx from daily bars)": low_52w if low_52w is not None else "N/A",
        "Primary exchange": r.get("primary_exchange", "N/A"),
        "List date": r.get("list_date", "N/A"),
        "Employees (approx)": r.get("total_employees", "N/A"),
        "Weighted shares outstanding": r.get("weighted_shares_outstanding", "N/A"),
        "PE / Beta / margins": "N/A (not on Polygon ticker overview; use filings or another feed)",
    }
    lines = [f"**{k}**: {v}" for k, v in fields.items()]
    out = "**Source: Polygon.io**\n\n" + "\n".join(lines)
    desc = r.get("description") or ""
    if desc:
        out += f"\n\n**Business description**: {desc[:900]}"
    return out


def _get_price_history_polygon(ticker: str, period: str = "1y") -> str:
    t = ticker.upper()
    days = {"3mo": 100, "6mo": 190, "1y": 400, "2y": 800}.get(period, 400)
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    path = f"/v2/aggs/ticker/{t}/range/1/month/{from_d.isoformat()}/{to_d.isoformat()}"
    data = _polygon_get(
        path,
        {"adjusted": "true", "sort": "asc", "limit": 500},
    )
    bars = data.get("results") or []
    if not bars:
        return f"No Polygon monthly bars for '{ticker}'."
    lines = []
    for b in bars:
        ts_ms = b.get("t")
        c = b.get("c")
        if ts_ms is None or c is None:
            continue

        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        lines.append(f"{d.strftime('%Y-%m')}: ${float(c):.2f}")
    if not lines:
        return f"No usable Polygon monthly prices for '{ticker}'."
    return "## Monthly Closing Prices (Polygon.io)\n" + "\n".join(lines)


def _format_financial_block(title: str, obj: Any, budget: int) -> tuple[str, int]:
    if obj is None or obj == {}:
        return "", budget
    raw = json.dumps(obj, indent=2, default=str)
    if len(raw) <= budget:
        return f"## {title}\n{raw}\n", 0
    return f"## {title}\n{raw[:budget]}\n... (truncated)\n", 0


def _get_financial_statements_polygon(ticker: str) -> str:
    """Uses vX reference financials (plan-dependent). Newer /v1 financials APIs may apply on higher tiers."""
    t = ticker.upper()
    try:
        data = _polygon_get(
            "/vX/reference/financials",
            {"ticker": t, "limit": 4, "timeframe": "annual"},
        )
    except RuntimeError as e:
        return (
            f"Polygon financials unavailable for '{ticker}': {e}\n"
            "Your Polygon plan may require Stock Financials access, or use the newer "
            "stocks/financials/v* endpoints per Polygon docs. Fallback: unset POLYGON_API_KEY "
            "to use yfinance for this tool only is not automatic; add yfinance path if needed."
        )

    results = data.get("results") or []
    if not results:
        return f"No Polygon financial filings returned for '{ticker}'."

    parts: list[str] = ["**Source: Polygon.io (SEC-derived financials)**\n"]
    budget = 14000
    for i, row in enumerate(results):
        if budget < 500:
            parts.append("\n... further filing periods omitted ...")
            break
        header = (
            f"### Filing {i + 1}: period_of_report "
            f"{row.get('period_of_report_date', 'N/A')} "
            f"filing_date {row.get('filing_date', 'N/A')}\n"
        )
        parts.append(header)
        fin = row.get("financials") or {}
        for key, title in (
            ("income_statement", "Income statement"),
            ("balance_sheet", "Balance sheet"),
            ("cash_flow_statement", "Cash flow statement"),
        ):
            block, _ = _format_financial_block(title, fin.get(key), min(budget, 4500))
            if block:
                parts.append(block)
                budget -= len(block)
    return "\n".join(parts) if len(parts) > 1 else f"No structured financials in Polygon response for '{ticker}'."


# ── Public API (Polygon if configured, else yfinance) ─────────────────


@logged_tool("get_stock_info")
async def get_stock_info(ticker: str) -> str:
    """Return company summary and key metrics."""
    if _use_polygon():
        try:
            return _get_stock_info_polygon(ticker)
        except Exception as e:
            logger.exception("Polygon get_stock_info failed")
            return f"Polygon stock info failed for '{ticker}': {e}"
    return _get_stock_info_yfinance(ticker)


def _get_stock_info_yfinance(ticker: str) -> str:
    stock = yf.Ticker(ticker)
    info = stock.info
    if not info or info.get("regularMarketPrice") is None:
        return f"No data found for ticker '{ticker}'. Please verify the symbol."

    fields = {
        "Company": info.get("longName", "N/A"),
        "Sector": info.get("sector", "N/A"),
        "Industry": info.get("industry", "N/A"),
        "Country": info.get("country", "N/A"),
        "Market Cap": info.get("marketCap", "N/A"),
        "Current Price": info.get("regularMarketPrice", info.get("currentPrice", "N/A")),
        "52-Week High": info.get("fiftyTwoWeekHigh", "N/A"),
        "52-Week Low": info.get("fiftyTwoWeekLow", "N/A"),
        "PE Ratio (TTM)": info.get("trailingPE", "N/A"),
        "Forward PE": info.get("forwardPE", "N/A"),
        "PB Ratio": info.get("priceToBook", "N/A"),
        "Dividend Yield": info.get("dividendYield", "N/A"),
        "Beta": info.get("beta", "N/A"),
        "Profit Margin": info.get("profitMargins", "N/A"),
        "Revenue Growth": info.get("revenueGrowth", "N/A"),
        "Earnings Growth": info.get("earningsGrowth", "N/A"),
    }
    summary = info.get("longBusinessSummary", "")
    lines = [f"**{k}**: {v}" for k, v in fields.items()]
    result = "**Source: Yahoo Finance (yfinance)**\n\n" + "\n".join(lines)
    if summary:
        result += f"\n\n**Business Summary**: {summary[:600]}"
    return result


@logged_tool("get_financial_statements")
async def get_financial_statements(ticker: str) -> str:
    """Return recent financial statement highlights."""
    if _use_polygon():
        try:
            return _get_financial_statements_polygon(ticker)
        except Exception as e:
            logger.exception("Polygon get_financial_statements failed")
            return f"Polygon financials failed for '{ticker}': {e}"
    return _get_financial_statements_yfinance(ticker)


def _get_financial_statements_yfinance(ticker: str) -> str:
    stock = yf.Ticker(ticker)
    parts: list[str] = []

    inc = stock.financials
    if inc is not None and not inc.empty:
        parts.append("## Income Statement (Annual)\n" + inc.to_string())

    bs = stock.balance_sheet
    if bs is not None and not bs.empty:
        parts.append("## Balance Sheet (Annual)\n" + bs.to_string())

    cf = stock.cashflow
    if cf is not None and not cf.empty:
        parts.append("## Cash Flow Statement (Annual)\n" + cf.to_string())

    if not parts:
        return f"No financial statements available for '{ticker}'."
    return "**Source: Yahoo Finance (yfinance)**\n\n" + "\n\n".join(parts)


@logged_tool("get_price_history")
async def get_price_history(ticker: str, period: str = "1y") -> str:
    """Return recent price history as a text table."""
    if _use_polygon():
        try:
            return _get_price_history_polygon(ticker, period)
        except Exception as e:
            logger.exception("Polygon get_price_history failed")
            return f"Polygon price history failed for '{ticker}': {e}"
    return _get_price_history_yfinance(ticker, period)


def _get_price_history_yfinance(ticker: str, period: str = "1y") -> str:
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty:
        return f"No price history available for '{ticker}'."
    monthly = hist["Close"].resample("ME").last().dropna()
    lines = [f"{d.strftime('%Y-%m')}: ${v:.2f}" for d, v in monthly.items()]
    return "**Source: Yahoo Finance (yfinance)**\n\n## Monthly Closing Prices\n" + "\n".join(lines)
