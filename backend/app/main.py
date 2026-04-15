"""FastAPI application entry point."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.routers import advisor, credit
from app.storage import ConversationStore, store as _store_singleton

logger = logging.getLogger(__name__)

# ── Startup timestamp (for uptime) ──────────────────────────────────
_start_time: float = 0.0

#异步生命周期上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()
    # Startup: initialise conversation storage (async PostgreSQL)
    _store_singleton.__init__(settings.DATABASE_URL, settings.VECTOR_DIMENSIONS)
    await _store_singleton.init()
    yield
    # Shutdown
    await _store_singleton.close()


app = FastAPI(title=settings.APP_TITLE, lifespan=lifespan)

# ── Rate limiting ───────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Audit logging middleware ────────────────────────────────────────
from app.middleware.audit import AuditMiddleware  # noqa: E402

app.add_middleware(AuditMiddleware)


# ── API key authentication middleware ───────────────────────────────
@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Skip auth if API_KEY is not configured (dev mode)
    if not settings.API_KEY:
        return await call_next(request)

    path = request.url.path
    # Exempt health check and static/docs paths
    if path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key", "")
    if api_key != settings.API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key."})

    return await call_next(request)


# ── Routers ─────────────────────────────────────────────────────────
app.include_router(advisor.router, prefix="/api/advisor", tags=["advisor"])
app.include_router(credit.router, prefix="/api/credit", tags=["credit"])


# ── Global exception handler (hardened) ─────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ── Health check (enhanced) ─────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    db_ok = False
    try:
        if _store_singleton._pool is not None:
            async with _store_singleton._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
    except Exception:
        pass

    uptime_s = round(time.time() - _start_time, 1) if _start_time else 0

    return {
        "status": "ok" if db_ok else "degraded",
        "db_connected": db_ok,
        "uptime_seconds": uptime_s,
    }


# ── Admin endpoints ─────────────────────────────────────────────────

@app.get("/api/admin/error-logs/recent")
async def get_error_logs_recent(limit: int = 20):
    """Get recent error logs for monitoring."""
    lim = min(max(limit, 1), 100)
    logs = await _store_singleton.get_error_logs(limit=lim)
    return {"count": len(logs), "errors": logs}


@app.get("/api/admin/error-logs/{conversation_id}")
async def get_error_logs_for_conversation(conversation_id: str, limit: int = 20):
    """Get error logs for a specific conversation."""
    logs = await _store_singleton.get_error_logs(conversation_id=conversation_id, limit=limit)
    return {"conversation_id": conversation_id, "count": len(logs), "errors": logs}


@app.post("/api/admin/backfill-memory")
async def backfill_memory(limit: int = 100):
    """Backfill memory chunks for existing conversations (idempotent)."""
    from app.memory_ingest import backfill_all

    results = await backfill_all(limit=limit)
    return {"backfilled_conversations": len(results), "details": results}


@app.get("/api/admin/audit-stats")
async def audit_stats():
    """Return request counts per endpoint since last restart."""
    from app.middleware.audit import get_request_counts

    return {"since_start": round(time.time() - _start_time, 1) if _start_time else 0, "counts": get_request_counts()}


@app.get("/api/admin/tool-logs/stats")
async def get_tool_logs_stats():
    """Get aggregated tool call statistics for the last 24 hours."""
    async with _store_singleton.pool.acquire() as conn:
        # Tool usage stats
        tool_stats = await conn.fetch(
            """
            SELECT tool_name, COUNT(*) as call_count,
                   AVG(call_duration_ms) as avg_duration_ms,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
            FROM tool_call_logs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY tool_name
            ORDER BY call_count DESC
            """
        )

        # Data source stats
        source_stats = await conn.fetch(
            """
            SELECT data_source, COUNT(*) as call_count
            FROM tool_call_logs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY data_source
            ORDER BY call_count DESC
            """
        )

    return {
        "period": "24h",
        "tool_stats": [dict(r) for r in tool_stats],
        "source_stats": [dict(r) for r in source_stats]
    }


@app.get("/api/admin/tool-logs/recent")
async def get_tool_logs_recent(limit: int = 50):
    """Latest tool calls globally (initial analysis often logs under conversation_id=unknown)."""
    lim = min(max(limit, 1), 200)
    logs = await _store_singleton.get_tool_logs_recent(lim)
    return {"count": len(logs), "tool_calls": logs}


@app.get("/api/admin/tool-logs/{conversation_id}")
async def get_tool_logs(conversation_id: str, limit: int = 20):
    """Get tool call summaries for one conversation (see /recent for global tail)."""
    logs = await _store_singleton.get_tool_logs_for_conversation(conversation_id, limit)
    return {
        "conversation_id": conversation_id,
        "total_logs": len(logs),
        "tool_calls": logs
    }


@app.get("/api/admin/memory/{conversation_id}")
async def get_memory_status(conversation_id: str):
    """Get memory compression and reflection status for a conversation."""
    try:
        conv = await _store_singleton.get_conversation(conversation_id)
        if not conv:
            return JSONResponse(status_code=404, content={"detail": "Conversation not found"})

        latest_turn = await _store_singleton.get_latest_turn(conversation_id)
        summaries = await _store_singleton.get_summaries(conversation_id)
        meta_memories = await _store_singleton.get_meta_memories(conversation_id)

        return {
            "conversation_id": conversation_id,
            "ticker": conv.get("ticker"),
            "total_turns": latest_turn,
            "last_compressed_turn": conv.get("last_compressed_turn", 0),
            "last_reflection_turn": conv.get("last_reflection_turn", 0),
            "summaries": [
                {
                    "id": s["id"],
                    "turn_range": s.get("turn_range"),
                    "message_count": s.get("message_count"),
                    "content_preview": s["content"][:200] + "..." if len(s["content"]) > 200 else s["content"],
                    "created_at": s.get("created_at"),
                }
                for s in summaries
            ],
            "meta_memories": [
                {
                    "id": m["id"],
                    "type": m["memory_type"],
                    "content": m["content"],
                    "confidence": m.get("confidence"),
                    "turn_range": m.get("turn_range"),
                }
                for m in meta_memories
            ],
        }
    except Exception as e:
        logger.error(f"Failed to get memory status: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/memory/compress/{conversation_id}")
async def force_memory_compression(conversation_id: str):
    """Force memory compression for a conversation."""
    from app.memory_compression import check_and_compress_memory

    try:
        result = await check_and_compress_memory(conversation_id)
        return {
            "conversation_id": conversation_id,
            "compression_triggered": result,
        }
    except Exception as e:
        logger.error(f"Failed to compress memory: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/memory/reflect/{conversation_id}")
async def force_memory_reflection(conversation_id: str):
    """Force self-reflection for a conversation."""
    from app.memory_reflection import trigger_reflection

    try:
        latest_turn = await _store_singleton.get_latest_turn(conversation_id)
        reflections = await trigger_reflection(conversation_id, latest_turn)
        return {
            "conversation_id": conversation_id,
            "current_turn": latest_turn,
            "reflections_generated": len(reflections),
            "reflections": [
                {
                    "type": r["type"],
                    "content": r["content"],
                    "confidence": r.get("confidence"),
                }
                for r in reflections
            ],
        }
    except Exception as e:
        logger.error(f"Failed to trigger reflection: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})
