"""
自动化评估 CLI（需在 backend 目录执行，以便加载 app 包）。

示例:
  python -m eval.cli run --dataset eval/golden_sample.jsonl --out outputs/eval_run_001
  python -m eval.cli judge --runs outputs/eval_run_001
  python -m eval.cli report --judged outputs/eval_run_001 --out outputs/eval_run_001/report.json
  python -m eval.cli pipeline --dataset eval/golden_sample.jsonl --out outputs/eval_run_001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# backend/ 作为 cwd 时，将项目根加入 path（兼容从 repo 根目录 python -m eval.cli）
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from eval.dataset import load_jsonl
from eval.judge import judge_file, write_judged
from eval.reporter import build_report, load_judged_dir, write_report
from eval.runner import run_single_case, write_run, ensure_store


async def cmd_run(args: argparse.Namespace) -> None:
    cases = load_jsonl(Path(args.dataset))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    await ensure_store()
    for case in cases:
        rec = await run_single_case(case)
        write_run(rec, out / f"{case.id}.json")
        print(f"[run] {case.id} error={rec.get('error')} wall_ms={rec.get('wall_clock_ms')}")
    await store_close_if_cli()


async def cmd_judge(args: argparse.Namespace) -> None:
    run_dir = Path(args.runs)
    for p in sorted(run_dir.glob("*.json")):
        if p.name.endswith(".judged.json") or p.name == "report.json":
            continue
        out_p = p.with_suffix(".judged.json")
        await judge_file(p, out_p)
        print(f"[judge] {p.name} -> {out_p.name}")


def cmd_report(args: argparse.Namespace) -> None:
    judged_dir = Path(args.judged)
    rows = load_judged_dir(judged_dir)
    if not rows:
        alt = list(judged_dir.glob("*.json"))
        rows = [json.loads(p.read_text(encoding="utf-8")) for p in alt if p.name.endswith(".judged.json")]
    rep = build_report(rows)
    out_path = Path(args.out)
    write_report(rep, out_path)
    print(json.dumps(rep, ensure_ascii=False, indent=2))


async def cmd_pipeline(args: argparse.Namespace) -> None:
    cases = load_jsonl(Path(args.dataset))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    await ensure_store()
    for case in cases:
        rec = await run_single_case(case)
        write_run(rec, out / f"{case.id}.json")
        print(f"[run] {case.id} error={rec.get('error')}")
        if not rec.get("error"):
            from eval.judge import judge_run_record

            judged = await judge_run_record(rec)
            write_judged(judged, out / f"{case.id}.judged.json")
            print(f"[judge] {case.id} overall={ (judged.get('judge_output') or {}).get('overall_1_5') }")

    rows = load_judged_dir(out)
    rep = build_report(rows)
    write_report(rep, out / "report.json")
    print("[report]", json.dumps(rep, ensure_ascii=False))
    await store_close_if_cli()


async def store_close_if_cli() -> None:
    from app.storage import store

    if store._pool is not None:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Advisor eval: run / judge / report / pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run golden set, write *.json traces")
    p_run.add_argument("--dataset", required=True, help="Path to JSONL golden file")
    p_run.add_argument("--out", required=True, help="Output directory")
    p_run.set_defaults(func=lambda a: asyncio.run(cmd_run(a)))

    p_j = sub.add_parser("judge", help="LLM-judge existing *.json runs")
    p_j.add_argument("--runs", required=True, help="Directory with run outputs")
    p_j.set_defaults(func=lambda a: asyncio.run(cmd_judge(a)))

    p_r = sub.add_parser("report", help="Aggregate *.judged.json")
    p_r.add_argument("--judged", required=True, help="Directory with judged files")
    p_r.add_argument("--out", required=True, help="report.json path")
    p_r.set_defaults(func=cmd_report)

    p_p = sub.add_parser("pipeline", help="run + judge + report in one go")
    p_p.add_argument("--dataset", required=True)
    p_p.add_argument("--out", required=True)
    p_p.set_defaults(func=lambda a: asyncio.run(cmd_pipeline(a)))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
