"""LLM-as-a-Judge: score run outputs from saved JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from autogen_agentchat.messages import UserMessage

from app.agents.llm_config import get_model_client


_JUDGE_SYSTEM = """你是严谨的评估裁判（LLM-as-a-Judge）。根据用户任务、可选参考答案、模型最终回答、以及执行轨迹摘要，输出**仅一段 JSON**（不要 Markdown 代码围栏，不要其它文字）。
评分维度均为 1–5 分（5 最好）。若信息不足，在 notes 中说明。

JSON 结构必须严格为：
{
  "scores": {
    "task_fulfillment": <int 1-5>,
    "correctness_vs_reference": <int 1-5>,
    "clarity": <int 1-5>,
    "safety_and_grounding": <int 1-5>,
    "tool_use_reasoning": <int 1-5>
  },
  "overall_1_5": <float>,
  "route_match": <true|false|null>,
  "verdict": "<一句中文结论>",
  "notes": "<可选，简短>"
}

若题目与股票无关且系统正确拒绝，task_fulfillment 与 safety_and_grounding 可给高分。
tool_use_reasoning：根据轨迹中是否出现合理工具调用/推理链给分；若无工具调用但任务不需要工具，可给 4–5。
route_match：仅当提供了 expected_route 时填 true/false，否则 null。
overall_1_5 为各维度加权主观总评，范围 1–5。"""


def _compact_trace_for_judge(trace: dict[str, Any] | None, max_msgs: int = 40) -> str:
    if not trace:
        return "(无轨迹)"
    lines: list[str] = []
    t = trace.get("timings_ms") or {}
    lines.append(f"timings_ms: {t}")
    tok = trace.get("token_totals") or {}
    if tok:
        lines.append(f"token_totals: {tok}")
    msgs = trace.get("agent_messages") or []
    lines.append(f"message_count: {len(msgs)}")
    for i, m in enumerate(msgs[:max_msgs]):
        src = m.get("source")
        typ = m.get("type")
        u = m.get("usage")
        preview = (m.get("content") or "")[:800]
        lines.append(f"[{i}] {src} | {typ} | usage={u}\n{preview}")
    if len(msgs) > max_msgs:
        lines.append(f"... 省略 {len(msgs) - max_msgs} 条")
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", text)
    if m:
        text = m.group(0)
    return json.loads(text)


async def judge_run_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return record merged with judge_output; does not write file."""
    if record.get("error"):
        return {
            **record,
            "judge_output": {
                "skipped": True,
                "reason": "run failed",
            },
        }

    expected = record.get("expected_route")
    ref = record.get("reference_answer") or "(未提供参考答案)"
    criteria = record.get("judge_criteria") or "(未提供额外标准)"
    trace_blob = _compact_trace_for_judge(record.get("trace"))

    user_block = f"""## 任务
标的: {record.get("ticker")}
用户问题: {record.get("question")}

## 参考答案（可能为空）
{ref}

## 额外评判标准
{criteria}

## 路由结果
{json.dumps(record.get("routing"), ensure_ascii=False)}

## 期望路由（若为空则 JSON 中 route_match 置 null）
{json.dumps(expected, ensure_ascii=False)}

## 模型最终回答
{record.get("answer") or ""}

## 执行轨迹摘要
{trace_blob}
"""

    prompt = _JUDGE_SYSTEM + "\n\n" + user_block
    client = get_model_client()
    result = await client.create([UserMessage(content=prompt, source="eval_judge")])
    raw = (result.content or "").strip()
    judge_usage: dict[str, int] | None = None
    u = getattr(result, "usage", None)
    if u is not None:
        judge_usage = {
            "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        }

    try:
        parsed = _extract_json_object(raw)
    except (json.JSONDecodeError, ValueError):
        parsed = {
            "scores": {},
            "overall_1_5": None,
            "route_match": None,
            "verdict": "解析裁判 JSON 失败",
            "notes": raw[:2000],
            "raw_response": raw,
        }

    exp = record.get("expected_route")
    routing = record.get("routing") or {}
    if exp and routing.get("route") is not None:
        parsed["route_match"] = routing.get("route") == exp

    out = {**record, "judge_output": parsed, "judge_raw": raw}
    if judge_usage is not None:
        out["judge_usage"] = judge_usage
    return out


def write_judged(record: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


async def judge_file(run_json: Path, out_json: Path | None = None) -> dict[str, Any]:
    data = json.loads(run_json.read_text(encoding="utf-8"))
    judged = await judge_run_record(data)
    path = out_json or run_json.with_suffix(".judged.json")
    write_judged(judged, path)
    return judged
