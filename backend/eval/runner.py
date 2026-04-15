"""Execute golden cases against run_followup and persist traces."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.agents.group_chat import run_followup
from app.config import settings
from app.storage import store

from .schema import GoldenCase


async def ensure_store() -> None:
    if store._pool is None:
        store.__init__(settings.DATABASE_URL, settings.VECTOR_DIMENSIONS)
        await store.init()


async def run_single_case(case: GoldenCase) -> dict[str, Any]:
    """Create a fresh conversation, optional seed, user turn, then follow-up with trace."""
    await ensure_store()

    conv = await store.create_conversation(case.ticker)
    cid = conv["id"]

    if case.seed_assistant_report:
        t = await store.get_latest_turn(cid) + 1
        await store.add_message(
            cid, t, "Investment_Advisor", case.seed_assistant_report, "agent_message",
        )

    if case.context:
        t = await store.get_latest_turn(cid) + 1
        await store.add_message(cid, t, "user", case.context, "user_message")

    t = await store.get_latest_turn(cid) + 1
    await store.add_message(cid, t, "user", case.question, "user_message")

    t0 = time.perf_counter()
    err: str | None = None
    answer = ""
    routing: dict[str, Any] = {}
    trace: dict[str, Any] | None = None
    try:
        out = await run_followup(
            case.ticker, case.question, cid, collect_trace=True,
        )
        answer, decision, trace = out
        routing = {
            "route": decision.route,
            "confidence": decision.confidence,
            "source": decision.source,
            "rationale": decision.rationale,
            "requires_fresh_data": decision.requires_fresh_data,
            "metadata": decision.metadata or {},
        }
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    wall_ms = int((time.perf_counter() - t0) * 1000)

    record: dict[str, Any] = {
        "case_id": case.id,
        "ticker": case.ticker,
        "question": case.question,
        "reference_answer": case.reference_answer,
        "judge_criteria": case.judge_criteria,
        "expected_route": case.expected_route,
        "conversation_id": cid,
        "routing": routing,
        "answer": answer,
        "trace": trace,
        "error": err,
        "wall_clock_ms": wall_ms,
    }
    if trace and "timings_ms" in trace:
        record["pipeline_timings_ms"] = trace["timings_ms"]
    return record


def write_run(record: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
