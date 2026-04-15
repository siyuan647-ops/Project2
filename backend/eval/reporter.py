"""Aggregate judged runs into a summary report."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any


def load_judged_dir(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted(directory.glob("*.judged.json")):
        rows.append(json.loads(p.read_text(encoding="utf-8")))
    return rows


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [r for r in rows if not (r.get("judge_output") or {}).get("skipped")]
    skipped = [r for r in rows if (r.get("judge_output") or {}).get("skipped")]

    overall_scores: list[float] = []
    route_ok = 0
    route_total = 0
    dim_acc: dict[str, list[float]] = {}

    for r in judged:
        jo = r.get("judge_output") or {}
        ov = jo.get("overall_1_5")
        if isinstance(ov, (int, float)):
            overall_scores.append(float(ov))
        scores = jo.get("scores") or {}
        if isinstance(scores, dict):
            for k, v in scores.items():
                if isinstance(v, (int, float)):
                    dim_acc.setdefault(k, []).append(float(v))

        exp = r.get("expected_route")
        if exp and jo.get("route_match") is not None:
            route_total += 1
            if jo.get("route_match") is True:
                route_ok += 1

    timings = []
    tokens = []
    for r in rows:
        pt = (r.get("trace") or {}).get("timings_ms") or r.get("pipeline_timings_ms")
        if isinstance(pt, dict) and "total_followup" in pt:
            timings.append(pt["total_followup"])
        tt = (r.get("trace") or {}).get("token_totals") or {}
        if isinstance(tt, dict) and "total_tokens" in tt:
            tokens.append(tt["total_tokens"])

    report: dict[str, Any] = {
        "case_count": len(rows),
        "judged_count": len(judged),
        "skipped_count": len(skipped),
        "mean_overall_1_5": round(mean(overall_scores), 3) if overall_scores else None,
        "dimension_means": {k: round(mean(v), 3) for k, v in sorted(dim_acc.items())},
        "route_match_rate": round(route_ok / route_total, 3) if route_total else None,
        "route_match_count": f"{route_ok}/{route_total}" if route_total else None,
        "latency_ms_mean": round(mean(timings), 1) if timings else None,
        "tokens_mean": round(mean(tokens), 1) if tokens else None,
        "failures": [
            {"case_id": r.get("case_id"), "error": r.get("error")}
            for r in rows
            if r.get("error")
        ],
    }
    return report


def write_report(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
