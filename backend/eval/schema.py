"""Golden dataset row schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenCase:
    """One eval case: follow-up style (conversation may be seeded)."""

    id: str
    ticker: str
    question: str
    reference_answer: str = ""
    context: str = ""
    seed_assistant_report: str = ""
    expected_route: str | None = None
    judge_criteria: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GoldenCase:
        return cls(
            id=str(d.get("id") or d.get("case_id") or ""),
            ticker=str(d["ticker"]),
            question=str(d["question"]),
            reference_answer=str(d.get("reference_answer") or d.get("reference") or ""),
            context=str(d.get("context") or ""),
            seed_assistant_report=str(d.get("seed_assistant_report") or ""),
            expected_route=d.get("expected_route"),
            judge_criteria=str(d.get("judge_criteria") or ""),
        )

    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.id:
            errs.append("missing id")
        if not self.ticker:
            errs.append("missing ticker")
        if not self.question:
            errs.append("missing question")
        return errs
