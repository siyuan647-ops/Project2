#!/usr/bin/env python3
r"""
Backend-focused checks for the investment advisor (plan: 后端问题排查方案).

Steps:
  A) GET /api/health
  B) POST/GET /api/advisor/conversations
  C) POST .../initial (SSE): TTFB, presence of agent_message (uses curl if available)
  D) What to watch in uvicorn logs (printed checklist)
  E) Same-host deps: yfinance, optional Tavily, optional Kimi

Usage (from repo root):
  cd backend && python ../scripts/check_backend_advisor.py
  python ../scripts/check_backend_advisor.py --base http://127.0.0.1:8000 --ticker AAPL --stream-seconds 60

If API_KEY is set in backend/.env, it is sent as X-API-Key automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "backend"


def _load_backend_env() -> None:
    backend = _backend_dir()
    sys.path.insert(0, str(backend))
    os.chdir(backend)
    try:
        from dotenv import load_dotenv

        load_dotenv(backend / ".env")
    except ImportError:
        pass


def _http_json(
    method: str,
    url: str,
    *,
    data: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict | list | str]:
    h = {"Accept": "application/json", **(headers or {})}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
    try:
        parsed: dict | list | str = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        parsed = raw
    return status, parsed


def step_a_health(base: str) -> bool:
    url = base.rstrip("/") + "/api/health"
    print("=== Step A: GET /api/health ===")
    t0 = time.perf_counter()
    try:
        status, body = _http_json("GET", url, timeout=10.0)
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return False
    elapsed = time.perf_counter() - t0
    print(f"  HTTP {status} in {elapsed:.2f}s")
    if isinstance(body, dict):
        print(f"  status={body.get('status')!r} db_connected={body.get('db_connected')} uptime_seconds={body.get('uptime_seconds')}")
    else:
        print(f"  body: {str(body)[:500]}")
    ok = status == 200 and isinstance(body, dict) and body.get("db_connected") is True
    if status == 200 and isinstance(body, dict) and body.get("db_connected") is False:
        print("  WARN: db_connected=false — Postgres unreachable or pool error (see DATABASE_URL).")
    return status == 200


def step_b_conversations(base: str, ticker: str, api_key: str | None) -> str | None:
    print("\n=== Step B: POST + GET /api/advisor/conversations ===")
    h = {}
    if api_key:
        h["X-API-Key"] = api_key
    url_create = base.rstrip("/") + "/api/advisor/conversations"
    t0 = time.perf_counter()
    status, body = _http_json("POST", url_create, data={"ticker": ticker}, headers=h or None)
    print(f"  POST conversations -> HTTP {status} in {time.perf_counter() - t0:.2f}s")
    if status == 429:
        print("  FAIL: rate limited (RATE_LIMIT_ADVISOR). Wait or adjust config.")
        return None
    if status == 401:
        print("  FAIL: 401 — set X-API-Key to match backend API_KEY or clear API_KEY in .env for dev.")
        return None
    if status != 200 or not isinstance(body, dict):
        print(f"  body: {body!r}")
        return None
    cid = body.get("id")
    if not cid:
        print(f"  FAIL: no id in response: {body!r}")
        return None
    print(f"  conversation id: {cid}")

    url_get = base.rstrip("/") + f"/api/advisor/conversations/{cid}"
    t0 = time.perf_counter()
    status2, body2 = _http_json("GET", url_get, headers=h or None)
    print(f"  GET conversations/{{id}} -> HTTP {status2} in {time.perf_counter() - t0:.2f}s")
    if status2 != 200:
        print(f"  body: {body2!r}")
        return None
    print("  OK: non-streaming advisor API path works.")
    return str(cid)


def step_c_initial_sse(base: str, conv_id: str, api_key: str | None, max_seconds: int) -> None:
    print("\n=== Step C: POST .../initial (SSE) ===")
    url = base.rstrip("/") + f"/api/advisor/conversations/{conv_id}/initial"
    curl = shutil.which("curl")
    if curl:
        cmd = [
            curl,
            "-N",
            "-s",
            "-S",
            "-m",
            str(max_seconds),
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
        ]
        if api_key:
            cmd += ["-H", f"X-API-Key: {api_key}"]
        cmd += [
            "-d",
            "{}",
            "-w",
            "\n__METRICS__\nhttp_code:%{http_code}\ntime_starttransfer:%{time_starttransfer}\n",
            url,
        ]
        print(f"  Running: curl -N -m {max_seconds} POST .../initial")
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max_seconds + 5,
            )
        except subprocess.TimeoutExpired:
            print("  FAIL: curl subprocess timeout")
            return
        out = (proc.stdout or "") + (proc.stderr or "")
        elapsed = time.perf_counter() - t0
        m = re.search(r"http_code:(\d+)", out)
        ttfb = re.search(r"time_starttransfer:([\d.]+)", out)
        metrics_idx = out.rfind("__METRICS__")
        stream_body = out[:metrics_idx] if metrics_idx != -1 else out
        code = m.group(1) if m else "?"
        ttfb_s = ttfb.group(1) if ttfb else "?"
        print(f"  wall_clock ~{elapsed:.2f}s | curl http_code={code} time_starttransfer={ttfb_s}s (TTFB)")
        if "event: agent_message" in stream_body or '"sender"' in stream_body:
            n = stream_body.count("event: agent_message")
            print(f"  OK: saw SSE agent_message markers (count ~{n}).")
        else:
            print("  WARN: no agent_message events in captured window - backend may still be in tools/LLM,")
            print("        or stream exceeded -m limit before first yieldable text.")
        if proc.returncode != 0:
            print(f"  curl exit code: {proc.returncode}")
        tail = stream_body[-1200:] if len(stream_body) > 1200 else stream_body
        if tail.strip():
            print("  --- last 1.2k of stream body ---")
            print(tail)
    else:
        print("  curl not found on PATH; using urllib readline fallback (max %ds total)." % max_seconds)
        _step_c_urllib(base, conv_id, api_key, max_seconds)


def _step_c_urllib(base: str, conv_id: str, api_key: str | None, max_seconds: int) -> None:
    url = base.rstrip("/") + f"/api/advisor/conversations/{conv_id}/initial"
    h = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        h["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=b"{}", method="POST", headers=h)
    t0 = time.perf_counter()
    first_byte = None
    buf = ""
    try:
        resp = urllib.request.urlopen(req, timeout=max_seconds)
        try:
            resp.fp.raw._sock.settimeout(30.0)  # type: ignore[attr-defined]
        except Exception:
            pass
        while time.perf_counter() - t0 < max_seconds:
            if first_byte is None:
                first_byte = time.perf_counter() - t0
            line = resp.readline()
            if not line:
                break
            buf += line.decode("utf-8", errors="replace")
            if "agent_message" in buf:
                break
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return
    elapsed = time.perf_counter() - t0
    ttfb = first_byte if first_byte is not None else elapsed
    print(f"  ~TTFB first read {ttfb:.2f}s, total read window {elapsed:.2f}s")
    if "agent_message" in buf:
        print("  OK: saw agent_message in stream.")
    else:
        print("  WARN: no agent_message in buffered stream (may need longer window or curl).")


def step_d_uvicorn_hints() -> None:
    print("\n=== Step D: Uvicorn terminal (manual while repeating Step C) ===")
    print("  Start API with: uvicorn app.main:app --reload --log-level info")
    print("  Watch for:")
    print("    - Traceback / Unhandled exception -> backend bug")
    print("    - app.tools.stock_data / app.tools.news_search INFO lines -> tool latency")
    print("    - Long silence during initial analysis -> sync block (often yfinance / Yahoo)")
    print("  If using Docker/Nginx in front of SSE: disable proxy_buffering for the stream path.")


def step_e_deps(ticker: str) -> None:
    print("\n=== Step E: Same-host dependencies (no HTTP) ===")
    _load_backend_env()
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        for name, fn in [
            ("info", lambda: stock.info),
            ("financials", lambda: stock.financials),
            ("history(1y)", lambda: stock.history(period="1y")),
        ]:
            t0 = time.perf_counter()
            try:
                v = fn()
                extra = ""
                if hasattr(v, "shape"):
                    extra = f" shape={tuple(v.shape)}"
                elif isinstance(v, dict):
                    extra = f" keys={len(v)}"
                elif hasattr(v, "__len__"):
                    extra = f" rows={len(v)}"
                print(f"  yfinance {ticker}.{name} OK in {time.perf_counter() - t0:.2f}s{extra}")
            except Exception as e:
                print(f"  yfinance {ticker}.{name} FAIL after {time.perf_counter() - t0:.2f}s: {type(e).__name__}: {e}")
    except ImportError as e:
        print(f"  yfinance import failed: {e}")

    try:
        from app.config import settings

        if settings.TAVILY_API_KEY:
            from tavily import TavilyClient

            t0 = time.perf_counter()
            try:
                c = TavilyClient(api_key=settings.TAVILY_API_KEY)
                r = c.search(query=f"{ticker} news", max_results=2, search_depth="basic")
                print(f"  Tavily search OK in {time.perf_counter() - t0:.2f}s ({len(r.get('results', []))} results)")
            except Exception as e:
                print(f"  Tavily FAIL: {type(e).__name__}: {e}")
        else:
            print("  Tavily: skipped (no TAVILY_API_KEY)")

        if settings.KIMI_API_KEY:
            u = settings.KIMI_BASE_URL.rstrip("/") + "/chat/completions"
            payload = json.dumps(
                {
                    "model": settings.KIMI_MODEL_NAME,
                    "messages": [{"role": "user", "content": "Say ok."}],
                    "max_tokens": 6,
                }
            ).encode()
            req = urllib.request.Request(
                u,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.KIMI_API_KEY}",
                },
            )
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = json.loads(resp.read().decode())
                ch = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"  Kimi chat/completions OK in {time.perf_counter() - t0:.2f}s reply={ch!r}")
            except Exception as e:
                print(f"  Kimi FAIL: {type(e).__name__}: {e}")
        else:
            print("  Kimi: skipped (no KIMI_API_KEY)")
    except Exception as e:
        print(f"  Step E config/tools error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend checks for investment advisor API.")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--ticker", default="AAPL", help="Ticker for conversation + yfinance")
    parser.add_argument(
        "--stream-seconds",
        type=int,
        default=90,
        help="Max seconds for curl -m / read window on POST initial",
    )
    parser.add_argument("--skip-stream", action="store_true", help="Skip Step C (SSE initial)")
    parser.add_argument("--skip-deps", action="store_true", help="Skip Step E (yfinance/Tavily/Kimi)")
    args = parser.parse_args()

    _load_backend_env()
    try:
        from app.config import settings

        api_key = settings.API_KEY or None
    except Exception:
        api_key = os.environ.get("API_KEY") or None

    ok_a = step_a_health(args.base)
    if not ok_a:
        print("\nAbort: fix health endpoint / process first.")
        sys.exit(1)

    cid = step_b_conversations(args.base, args.ticker.upper().strip(), api_key)
    if not cid:
        print("\nAbort: conversation flow failed.")
        sys.exit(1)

    if not args.skip_stream:
        step_c_initial_sse(args.base, cid, api_key, args.stream_seconds)

    step_d_uvicorn_hints()

    if not args.skip_deps:
        step_e_deps(args.ticker.upper().strip())

    print("\nDone.")


if __name__ == "__main__":
    main()
