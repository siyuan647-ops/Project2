"""PostgreSQL + pgvector conversation & message storage for the advisor module."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
from asyncpg.exceptions import FeatureNotSupportedError
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ConversationStore:
    """Async repository backed by PostgreSQL + pgvector."""

    def __init__(self, database_url: str = "", vector_dimensions: int = 384):
        self._database_url = database_url
        self._vector_dimensions = vector_dimensions
        self._pool: asyncpg.Pool | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Create the connection pool, register pgvector, and ensure schema."""
        # register_vector requires type `vector` to exist; create extension before any pooled
        # connection runs _conn_init (otherwise fresh DB raises unknown type: public.vector).
        await self._ensure_pgvector_extension()
        self._pool = await asyncpg.create_pool(
            dsn=self._database_url,
            min_size=2,
            max_size=10,
            init=self._conn_init,
        )
        await self._create_tables()
        logger.info("ConversationStore connected to PostgreSQL.")

    async def _ensure_pgvector_extension(self) -> None:
        conn = await asyncpg.connect(self._database_url)
        try:
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except FeatureNotSupportedError as e:
                raise RuntimeError(
                    "PostgreSQL does not have the pgvector extension installed. "
                    "This app requires it for advisor memory (vector search).\n"
                    "Fix options:\n"
                    "  1) Use Docker: from project root run `docker compose up -d postgres` "
                    "(image pgvector/pgvector). Stop Windows PostgreSQL or change its port "
                    "if 5432 is already taken, then set DATABASE_URL to "
                    "postgresql://finapp:finapp_secret@127.0.0.1:5432/financial_platform\n"
                    "  2) Or install pgvector on your local PostgreSQL (see pgvector repo)."
                ) from e
        finally:
            await conn.close()

    @staticmethod
    async def _conn_init(conn: asyncpg.Connection) -> None:
        """Per-connection setup: register pgvector type codec."""
        await register_vector(conn)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("ConversationStore not initialised – call init() first")
        return self._pool

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        dim = self._vector_dimensions
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT PRIMARY KEY,
                    ticker      TEXT NOT NULL,
                    title       TEXT NOT NULL DEFAULT '',
                    status      TEXT NOT NULL DEFAULT 'active',
                    summary     TEXT NOT NULL DEFAULT '',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS messages (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    turn            INTEGER NOT NULL,
                    sender          TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    event_type      TEXT NOT NULL DEFAULT 'agent_message',
                    embedding       vector({dim}),
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                    ON messages(conversation_id, turn, created_at)
                """
            )

            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS memory_chunks (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    message_id      TEXT REFERENCES messages(id),
                    chunk_type      TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    embedding       vector({dim}),
                    importance      REAL NOT NULL DEFAULT 0.5,
                    turn            INTEGER,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chunks_conv
                    ON memory_chunks(conversation_id)
                """
            )

            # Unique constraint for idempotent chunk ingestion (Phase A3)
            await conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_idempotent
                    ON memory_chunks(conversation_id, message_id, chunk_type)
                    WHERE message_id IS NOT NULL
                """
            )

            # Phase C1: pgvector ANN indexes for semantic retrieval
            # ivfflat requires at least some rows; CREATE INDEX IF NOT EXISTS
            # is safe to run even on empty tables (index is built lazily).
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding_ivfflat
                    ON memory_chunks
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 20)
                """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_messages_embedding_ivfflat
                    ON messages
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 20)
                """
            )

            # Tool call logs for hallucination audit
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_call_logs (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id),
                    message_id      TEXT REFERENCES messages(id),
                    tool_name       TEXT NOT NULL,
                    tool_args       JSONB,
                    tool_result     TEXT NOT NULL,
                    result_summary  TEXT,
                    data_source     TEXT,
                    call_duration_ms INTEGER,
                    status          TEXT NOT NULL DEFAULT 'success',
                    error_message   TEXT,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tool_logs_conv_time
                    ON tool_call_logs(conversation_id, created_at DESC)
                """
            )

            # Performance metrics for system observability
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id),
                    message_id      TEXT REFERENCES messages(id),
                    metric_type     TEXT NOT NULL,  -- 'routing', 'tool_call', 'agent_execution', 'llm_call', 'total'
                    component       TEXT NOT NULL,  -- 具体组件名，如 'enhanced_router', 'react_analyst', 'followup'
                    duration_ms     INTEGER NOT NULL,
                    metadata        JSONB,          -- 额外信息，如 token_count, cache_hit, etc.
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_perf_metrics_conv
                    ON performance_metrics(conversation_id, metric_type, created_at DESC)
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_perf_metrics_type_time
                    ON performance_metrics(metric_type, created_at DESC)
                """
            )

            # Error logs for centralized error tracking
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS error_logs (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id),
                    message_id      TEXT REFERENCES messages(id),
                    error_type      TEXT NOT NULL,  -- 'routing_error', 'tool_error', 'agent_error', 'llm_error', 'system_error'
                    component       TEXT NOT NULL,  -- 发生错误的组件
                    error_message   TEXT NOT NULL,
                    error_detail    TEXT,           -- 详细堆栈或上下文
                    severity        TEXT NOT NULL DEFAULT 'error',  -- 'warning', 'error', 'critical'
                    metadata        JSONB,          -- 相关上下文信息
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_logs_conv
                    ON error_logs(conversation_id, created_at DESC)
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_logs_type_severity
                    ON error_logs(error_type, severity, created_at DESC)
                """
            )

            # Conversation summaries for sliding window memory compression
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    summary_type    TEXT NOT NULL DEFAULT 'compressed_history',
                    content         TEXT NOT NULL,
                    turn_range      TEXT,
                    message_count   INTEGER,
                    embedding       vector({dim}),
                    importance      REAL DEFAULT 0.7,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_summaries_conv
                    ON conversation_summaries(conversation_id, summary_type, created_at)
                """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_summaries_embedding
                    ON conversation_summaries
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 10)
                """
            )

            # Meta-memories for self-reflection (high-level cognition)
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS meta_memories (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    memory_type     TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    evidence        TEXT,
                    confidence      REAL DEFAULT 0.7,
                    turn_range      TEXT,
                    embedding       vector({dim}),
                    last_triggered  TIMESTAMPTZ,
                    trigger_count   INTEGER DEFAULT 1,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_meta_conv
                    ON meta_memories(conversation_id, memory_type)
                """
            )

            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_meta_embedding
                    ON meta_memories
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 10)
                """
            )

            # Conversation metadata for tracking compression/reflection state
            await conn.execute(
                """
                ALTER TABLE conversations
                ADD COLUMN IF NOT EXISTS last_compressed_turn INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS last_reflection_turn INTEGER DEFAULT 0
                """
            )

            # Agent traces for debugging and transparency
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_traces (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    turn            INTEGER NOT NULL,
                    agent_name      TEXT NOT NULL,
                    trace_type      TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    metadata        JSONB,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_traces_conv
                    ON agent_traces(conversation_id, turn, created_at DESC)
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_traces_type
                    ON agent_traces(trace_type, created_at DESC)
                """
            )

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    async def create_conversation(self, ticker: str) -> dict[str, Any]:
        conv_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        await self.pool.execute(
            "INSERT INTO conversations (id, ticker, title, status, summary, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'active', '', $4, $5)",
            conv_id, ticker, f"{ticker} 投资分析", now, now,
        )
        return await self.get_conversation(conv_id)  # type: ignore[return-value]

    async def get_conversation(self, conv_id: str) -> dict[str, Any] | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM conversations WHERE id = $1", conv_id,
        )
        return dict(row) if row else None

    async def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]

    async def update_conversation(self, conv_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now_utc()
        set_parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(fields.items(), start=1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(conv_id)
        set_clause = ", ".join(set_parts)
        await self.pool.execute(
            f"UPDATE conversations SET {set_clause} WHERE id = ${len(values)}",  # noqa: S608
            *values,
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        conversation_id: str,
        turn: int,
        sender: str,
        content: str,
        event_type: str = "agent_message",
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        await self.pool.execute(
            "INSERT INTO messages (id, conversation_id, turn, sender, content, event_type, embedding, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            msg_id, conversation_id, turn, sender, content, event_type, embedding, now,
        )
        # Touch conversation updated_at
        await self.pool.execute(
            "UPDATE conversations SET updated_at = $1 WHERE id = $2",
            now, conversation_id,
        )
        return {"id": msg_id, "conversation_id": conversation_id, "turn": turn,
                "sender": sender, "content": content, "event_type": event_type,
                "created_at": now}

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT id, conversation_id, turn, sender, content, event_type, created_at "
            "FROM messages WHERE conversation_id = $1 ORDER BY turn, created_at",
            conversation_id,
        )
        return [dict(r) for r in rows]

    async def get_latest_turn(self, conversation_id: str) -> int:
        row = await self.pool.fetchrow(
            "SELECT COALESCE(MAX(turn), 0) AS max_turn FROM messages WHERE conversation_id = $1",
            conversation_id,
        )
        return row["max_turn"] if row else 0

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 6,
    ) -> list[dict[str, Any]]:
        """Return the most recent *limit* messages (for the recent window)."""
        rows = await self.pool.fetch(
            "SELECT id, conversation_id, turn, sender, content, event_type, created_at "
            "FROM messages WHERE conversation_id = $1 "
            "ORDER BY turn DESC, created_at DESC LIMIT $2",
            conversation_id, limit,
        )
        rows_list = [dict(r) for r in rows]
        rows_list.reverse()  # restore chronological order
        return rows_list

    async def update_message_embedding(
        self, msg_id: str, embedding: list[float],
    ) -> None:
        """Back-fill the embedding vector for an existing message."""
        await self.pool.execute(
            "UPDATE messages SET embedding = $1 WHERE id = $2",
            embedding, msg_id,
        )

    # ------------------------------------------------------------------
    # Memory chunks
    # ------------------------------------------------------------------

    async def chunk_exists(
        self,
        conversation_id: str,
        message_id: str,
        chunk_type: str,
    ) -> bool:
        """Check whether a chunk for this (conversation, message, type) already exists."""
        row = await self.pool.fetchrow(
            "SELECT 1 FROM memory_chunks "
            "WHERE conversation_id = $1 AND message_id = $2 AND chunk_type = $3",
            conversation_id, message_id, chunk_type,
        )
        return row is not None

    async def add_memory_chunk(
        self,
        conversation_id: str,
        content: str,
        chunk_type: str,
        embedding: list[float] | None = None,
        message_id: str | None = None,
        importance: float = 0.5,
        turn: int | None = None,
    ) -> dict[str, Any]:
        chunk_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        await self.pool.execute(
            "INSERT INTO memory_chunks "
            "(id, conversation_id, message_id, chunk_type, content, embedding, importance, turn, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            chunk_id, conversation_id, message_id, chunk_type, content,
            embedding, importance, turn, now,
        )
        return {"id": chunk_id, "conversation_id": conversation_id,
                "chunk_type": chunk_type, "content": content,
                "importance": importance, "turn": turn, "created_at": now}

    async def search_similar_chunks(
        self,
        conversation_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve the most semantically similar memory chunks (cosine distance)."""
        rows = await self.pool.fetch(
            "SELECT id, conversation_id, message_id, chunk_type, content, "
            "importance, turn, created_at, "
            "(embedding <=> $1::vector) AS distance "
            "FROM memory_chunks "
            "WHERE conversation_id = $2 AND embedding IS NOT NULL "
            "ORDER BY distance ASC LIMIT $3",
            query_embedding, conversation_id, limit,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Tool call logs (for hallucination audit)
    # ------------------------------------------------------------------

    async def log_tool_call(
        self,
        conversation_id: str,
        tool_name: str,
        tool_args: dict,
        tool_result: str,
        data_source: str,
        duration_ms: int,
        status: str = "success",
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Record a tool invocation for audit and hallucination tracing."""
        import json

        log_id = uuid.uuid4().hex[:12]
        result_summary = tool_result[:500] + "..." if len(tool_result) > 500 else tool_result

        await self.pool.execute(
            """
            INSERT INTO tool_call_logs
            (id, conversation_id, tool_name, tool_args, tool_result,
             result_summary, data_source, call_duration_ms, status, error_message, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            log_id, conversation_id, tool_name,
            json.dumps(tool_args) if tool_args else None,
            tool_result, result_summary, data_source,
            duration_ms, status, error_message, _now_utc()
        )
        return {"id": log_id}

    async def get_recent_tool_logs(
        self, conversation_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get recent tool call logs for a conversation."""
        rows = await self.pool.fetch(
            """
            SELECT tool_name, result_summary, data_source, call_duration_ms, status, created_at
            FROM tool_call_logs
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            conversation_id, limit
        )
        return [dict(r) for r in rows]

    async def get_tool_logs_for_conversation(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retrieve tool call logs for a conversation (for audit)."""
        rows = await self.pool.fetch(
            """
            SELECT id, tool_name, tool_args, result_summary, data_source,
                   call_duration_ms, status, error_message, created_at
            FROM tool_call_logs
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            conversation_id, limit
        )
        return [dict(r) for r in rows]

    async def get_tool_logs_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent tool invocations across all conversations (debug / audit)."""
        rows = await self.pool.fetch(
            """
            SELECT id, conversation_id, tool_name, tool_args, result_summary, data_source,
                   call_duration_ms, status, error_message, created_at
            FROM tool_call_logs
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Performance metrics (for system observability)
    # ------------------------------------------------------------------

    async def log_performance_metric(
        self,
        metric_type: str,
        component: str,
        duration_ms: int,
        conversation_id: str | None = None,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Record a performance metric for observability."""
        import json

        metric_id = uuid.uuid4().hex[:12]
        await self.pool.execute(
            """
            INSERT INTO performance_metrics
            (id, conversation_id, message_id, metric_type, component, duration_ms, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            metric_id, conversation_id, message_id, metric_type, component,
            duration_ms, json.dumps(metadata) if metadata else None, _now_utc()
        )
        return {"id": metric_id}

    async def get_performance_metrics(
        self,
        metric_type: str | None = None,
        component: str | None = None,
        conversation_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get performance metrics with optional filtering."""
        conditions = []
        params = []
        param_idx = 1

        if metric_type:
            conditions.append(f"metric_type = ${param_idx}")
            params.append(metric_type)
            param_idx += 1
        if component:
            conditions.append(f"component = ${param_idx}")
            params.append(component)
            param_idx += 1
        if conversation_id:
            conditions.append(f"conversation_id = ${param_idx}")
            params.append(conversation_id)
            param_idx += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        rows = await self.pool.fetch(
            f"""
            SELECT id, conversation_id, message_id, metric_type, component,
                   duration_ms, metadata, created_at
            FROM performance_metrics
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
            *params, limit, offset
        )
        return [dict(r) for r in rows]

    async def get_avg_performance_by_component(
        self,
        metric_type: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Get average performance metrics grouped by component."""
        if metric_type:
            rows = await self.pool.fetch(
                """
                SELECT component,
                       COUNT(*) as call_count,
                       AVG(duration_ms) as avg_duration_ms,
                       MIN(duration_ms) as min_duration_ms,
                       MAX(duration_ms) as max_duration_ms,
                       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration_ms
                FROM performance_metrics
                WHERE metric_type = $1 AND created_at > now() - interval '1 hour' * $2
                GROUP BY component
                ORDER BY avg_duration_ms DESC
                """,
                metric_type, hours
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT component, metric_type,
                       COUNT(*) as call_count,
                       AVG(duration_ms) as avg_duration_ms,
                       MIN(duration_ms) as min_duration_ms,
                       MAX(duration_ms) as max_duration_ms
                FROM performance_metrics
                WHERE created_at > now() - interval '1 hour' * $1
                GROUP BY component, metric_type
                ORDER BY avg_duration_ms DESC
                """,
                hours
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Error logs (for centralized error tracking)
    # ------------------------------------------------------------------

    async def log_error(
        self,
        error_type: str,
        component: str,
        error_message: str,
        conversation_id: str | None = None,
        message_id: str | None = None,
        error_detail: str | None = None,
        severity: str = "error",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Record an error for centralized tracking."""
        import json
        import traceback

        error_id = uuid.uuid4().hex[:12]

        # If error_detail not provided, try to capture current stack trace
        if error_detail is None:
            error_detail = traceback.format_exc()

        await self.pool.execute(
            """
            INSERT INTO error_logs
            (id, conversation_id, message_id, error_type, component, error_message,
             error_detail, severity, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            error_id, conversation_id, message_id, error_type, component,
            error_message, error_detail, severity,
            json.dumps(metadata) if metadata else None, _now_utc()
        )
        return {"id": error_id}

    async def get_error_logs(
        self,
        error_type: str | None = None,
        component: str | None = None,
        severity: str | None = None,
        conversation_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get error logs with optional filtering."""
        conditions = []
        params = []
        param_idx = 1

        if error_type:
            conditions.append(f"error_type = ${param_idx}")
            params.append(error_type)
            param_idx += 1
        if component:
            conditions.append(f"component = ${param_idx}")
            params.append(component)
            param_idx += 1
        if severity:
            conditions.append(f"severity = ${param_idx}")
            params.append(severity)
            param_idx += 1
        if conversation_id:
            conditions.append(f"conversation_id = ${param_idx}")
            params.append(conversation_id)
            param_idx += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        rows = await self.pool.fetch(
            f"""
            SELECT id, conversation_id, message_id, error_type, component,
                   error_message, error_detail, severity, metadata, created_at
            FROM error_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
            *params, limit, offset
        )
        return [dict(r) for r in rows]

    async def get_error_summary(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Get error summary statistics."""
        rows = await self.pool.fetch(
            """
            SELECT error_type, component, severity, COUNT(*) as count
            FROM error_logs
            WHERE created_at > now() - interval '1 hour' * $1
            GROUP BY error_type, component, severity
            ORDER BY count DESC
            """,
            hours
        )

        total_errors = sum(r["count"] for r in rows)
        critical_errors = sum(r["count"] for r in rows if r["severity"] == "critical")

        return {
            "total_errors": total_errors,
            "critical_errors": critical_errors,
            "breakdown": [dict(r) for r in rows],
            "time_range_hours": hours,
        }

    # ------------------------------------------------------------------
    # Conversation summaries (for sliding window memory compression)
    # ------------------------------------------------------------------

    async def save_summary(
        self,
        conversation_id: str,
        content: str,
        summary_type: str = "compressed_history",
        turn_range: str | None = None,
        message_count: int | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Save a conversation summary (compressed history)."""
        summary_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        await self.pool.execute(
            """
            INSERT INTO conversation_summaries
            (id, conversation_id, summary_type, content, turn_range, message_count, embedding, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            summary_id, conversation_id, summary_type, content, turn_range, message_count, embedding, now,
        )
        return {"id": summary_id, "conversation_id": conversation_id, "content": content}

    async def get_summaries(
        self, conversation_id: str, summary_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get conversation summaries."""
        if summary_type:
            rows = await self.pool.fetch(
                """
                SELECT id, summary_type, content, turn_range, message_count, created_at
                FROM conversation_summaries
                WHERE conversation_id = $1 AND summary_type = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                conversation_id, summary_type, limit
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT id, summary_type, content, turn_range, message_count, created_at
                FROM conversation_summaries
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                conversation_id, limit
            )
        return [dict(r) for r in rows]

    async def search_summaries(
        self, conversation_id: str, query_embedding: list[float], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Search summaries by semantic similarity."""
        rows = await self.pool.fetch(
            """
            SELECT id, summary_type, content, turn_range, message_count, created_at,
                   (embedding <=> $1::vector) AS distance
            FROM conversation_summaries
            WHERE conversation_id = $2 AND embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT $3
            """,
            query_embedding, conversation_id, limit
        )
        return [dict(r) for r in rows]

    async def update_summary_embedding(
        self, summary_id: str, embedding: list[float]
    ) -> None:
        """Update the embedding vector for a summary."""
        await self.pool.execute(
            "UPDATE conversation_summaries SET embedding = $1 WHERE id = $2",
            embedding, summary_id
        )

    async def get_messages_in_range(
        self, conversation_id: str, start_turn: int, end_turn: int
    ) -> list[dict[str, Any]]:
        """Get messages within a specific turn range."""
        rows = await self.pool.fetch(
            """
            SELECT id, conversation_id, turn, sender, content, event_type, created_at
            FROM messages
            WHERE conversation_id = $1 AND turn >= $2 AND turn <= $3
            ORDER BY turn, created_at
            """,
            conversation_id, start_turn, end_turn
        )
        return [dict(r) for r in rows]

    async def archive_messages(
        self, messages: list[dict[str, Any]]
    ) -> None:
        """Soft delete messages by marking them as archived."""
        # For now, we'll just add an archived flag or move to archive table
        # Simpler approach: we keep them but filter in get_recent_messages
        pass  # Implementation depends on strategy - for now rely on turn-based filtering

    async def get_last_compressed_turn(self, conversation_id: str) -> int:
        """Get the last turn that was compressed."""
        row = await self.pool.fetchrow(
            "SELECT last_compressed_turn FROM conversations WHERE id = $1",
            conversation_id
        )
        return row["last_compressed_turn"] if row else 0

    async def update_last_compressed_turn(
        self, conversation_id: str, turn: int
    ) -> None:
        """Update the last compressed turn."""
        await self.pool.execute(
            "UPDATE conversations SET last_compressed_turn = $1 WHERE id = $2",
            turn, conversation_id
        )

    # ------------------------------------------------------------------
    # Meta-memories (for self-reflection)
    # ------------------------------------------------------------------

    async def save_meta_memory(
        self,
        conversation_id: str,
        memory_type: str,
        content: str,
        evidence: str | None = None,
        confidence: float = 0.7,
        turn_range: str | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """Save a meta-memory (high-level cognition)."""
        meta_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        await self.pool.execute(
            """
            INSERT INTO meta_memories
            (id, conversation_id, memory_type, content, evidence, confidence, turn_range, embedding, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            meta_id, conversation_id, memory_type, content, evidence, confidence, turn_range, embedding, now
        )
        return meta_id

    async def get_meta_memories(
        self, conversation_id: str, memory_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get meta-memories."""
        if memory_type:
            rows = await self.pool.fetch(
                """
                SELECT id, memory_type, content, evidence, confidence, turn_range, trigger_count, created_at
                FROM meta_memories
                WHERE conversation_id = $1 AND memory_type = $2
                ORDER BY confidence DESC, created_at DESC
                LIMIT $3
                """,
                conversation_id, memory_type, limit
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT id, memory_type, content, evidence, confidence, turn_range, trigger_count, created_at
                FROM meta_memories
                WHERE conversation_id = $1
                ORDER BY confidence DESC, created_at DESC
                LIMIT $2
                """,
                conversation_id, limit
            )
        return [dict(r) for r in rows]

    async def search_meta_memories(
        self, conversation_id: str, query_embedding: list[float], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Search meta-memories by semantic similarity."""
        rows = await self.pool.fetch(
            """
            SELECT id, memory_type, content, evidence, confidence, created_at,
                   (embedding <=> $1::vector) AS distance
            FROM meta_memories
            WHERE conversation_id = $2 AND embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT $3
            """,
            query_embedding, conversation_id, limit
        )
        return [dict(r) for r in rows]

    async def update_meta_memory_embedding(
        self, meta_id: str, embedding: list[float]
    ) -> None:
        """Update the embedding vector for a meta-memory."""
        await self.pool.execute(
            "UPDATE meta_memories SET embedding = $1 WHERE id = $2",
            embedding, meta_id
        )

    async def update_last_reflection_turn(self, conversation_id: str, turn: int) -> None:
        """Update the last reflection turn."""
        await self.pool.execute(
            "UPDATE conversations SET last_reflection_turn = $1 WHERE id = $2",
            turn, conversation_id
        )

    async def get_last_reflection_turn(self, conversation_id: str) -> int:
        """Get the last turn that triggered reflection."""
        row = await self.pool.fetchrow(
            "SELECT last_reflection_turn FROM conversations WHERE id = $1",
            conversation_id
        )
        return row["last_reflection_turn"] if row else 0

    # ------------------------------------------------------------------
    # Agent traces (for debugging and transparency)
    # ------------------------------------------------------------------

    async def log_agent_trace(
        self,
        conversation_id: str,
        turn: int,
        agent_name: str,
        trace_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Record an agent trace for debugging and transparency."""
        import json
        trace_id = uuid.uuid4().hex[:12]
        now = _now_utc()
        # Truncate content if too long
        if len(content) > 10000:
            content = content[:10000] + "\n... [truncated]"
        await self.pool.execute(
            """
            INSERT INTO agent_traces
            (id, conversation_id, turn, agent_name, trace_type, content, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            trace_id, conversation_id, turn, agent_name, trace_type,
            content, json.dumps(metadata) if metadata else None, now
        )
        return {"id": trace_id}

    async def get_agent_traces(
        self,
        conversation_id: str,
        trace_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get agent traces for a conversation."""
        if trace_type:
            rows = await self.pool.fetch(
                """
                SELECT id, conversation_id, turn, agent_name, trace_type, content, metadata, created_at
                FROM agent_traces
                WHERE conversation_id = $1 AND trace_type = $2
                ORDER BY created_at ASC
                LIMIT $3
                """,
                conversation_id, trace_type, limit
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT id, conversation_id, turn, agent_name, trace_type, content, metadata, created_at
                FROM agent_traces
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                conversation_id, limit
            )
        return [dict(r) for r in rows]

    async def get_agent_trace_summary(
        self,
        conversation_id: str,
    ) -> dict[str, Any]:
        """Get a summary of agent traces for a conversation."""
        rows = await self.pool.fetch(
            """
            SELECT
                trace_type,
                agent_name,
                COUNT(*) as count,
                MIN(created_at) as first_seen,
                MAX(created_at) as last_seen
            FROM agent_traces
            WHERE conversation_id = $1
            GROUP BY trace_type, agent_name
            ORDER BY count DESC
            """,
            conversation_id
        )
        return {
            "conversation_id": conversation_id,
            "trace_summary": [dict(r) for r in rows],
        }


# Module-level singleton – initialised in main.py startup
store = ConversationStore.__new__(ConversationStore)
store._database_url = ""
store._vector_dimensions = 384
store._pool = None
