"""Audit logging middleware – records every API request for compliance."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

audit_logger = logging.getLogger("audit")

# In-memory request counter (thread-safe) for /api/admin/audit-stats
_request_counts: dict[str, int] = defaultdict(int)
_counts_lock = Lock()


def get_request_counts() -> dict[str, int]:
    with _counts_lock:
        return dict(_request_counts)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        user_agent = request.headers.get("user-agent", "")

        response: Response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000, 1)
        status = response.status_code

        audit_logger.info(
            "%s %s %s %d %.1fms UA=%s",
            client_ip, method, path, status, duration_ms, user_agent[:120],
        )

        with _counts_lock:
            _request_counts[f"{method} {path}"] += 1

        return response
