"""Load golden cases from JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from .schema import GoldenCase


def load_jsonl(path: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
        c = GoldenCase.from_dict(row)
        errs = c.validate()
        if errs:
            raise ValueError(f"{path}:{line_no} case {c.id!r}: {', '.join(errs)}")
        cases.append(c)
    return cases
