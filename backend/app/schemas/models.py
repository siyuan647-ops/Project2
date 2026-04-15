"""Pydantic request / response models."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ── Advisor (legacy one-shot) ───────────────────────────────────────

class AdvisorRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Za-z0-9.]+$",
                        description="Stock ticker symbol, e.g. AAPL")


# ── Advisor conversations (multi-turn) ──────────────────────────────

class StartConversationRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Za-z0-9.]+$")


class FollowUpRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def reject_prompt_injection(cls, v: str) -> str:
        _INJECTION_PATTERNS = re.compile(
            r"ignore\s+(previous|above|all)\s+instructions"
            r"|system\s*:\s*you\s+are"
            r"|\bDAN\b.*\bjailbreak\b"
            r"|忽略.{0,6}(指令|规则|约束)"
            r"|你现在是.{0,10}(模式|角色)",
            re.IGNORECASE,
        )
        if _INJECTION_PATTERNS.search(v):
            raise ValueError("输入内容包含不允许的指令，请重新提问。")
        return v


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    turn: int
    sender: str
    content: str
    event_type: str
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    ticker: str
    title: str
    status: str
    summary: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class RoutingInfo(BaseModel):
    route: str
    confidence: float
    source: str
    rationale: str
    requires_fresh_data: bool


class InitialAnalysisResponse(BaseModel):
    conversation_id: str
    turn: int
    ticker: str
    report: str


class FollowUpResponse(BaseModel):
    conversation_id: str
    turn: int
    ticker: str
    answer: str
    routing: RoutingInfo


# ── Credit ──────────────────────────────────────────────────────────

class CreditPredictionMeta(BaseModel):
    filename: str
    total_records: int
    distribution: dict[str, int]
    warnings: list[str] = []
    model_version: str = ""
    prediction_timestamp: str = ""
    disclaimer: str = "信用评估结果由 AI 模型生成，仅供参考，不应作为唯一放贷依据。"
