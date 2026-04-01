"""FastAPI middleware for logging prediction metrics."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from tobira.monitoring.store import append_record

_DEFAULT_LOG_PATH = "/var/lib/tobira/predictions.jsonl"

logger = logging.getLogger(__name__)


class PredictionCollector:
    """Starlette middleware that logs prediction metrics to a JSONL file.

    Only ``POST /predict`` requests with a successful (2xx) response are logged.
    The logged record contains *timestamp*, *label*, *score*, and *latency_ms*.
    The request text is **never** logged for privacy protection.

    When a ``redis_url`` is provided, prediction scores are also pushed to a
    :class:`~tobira.monitoring.store.RedisScoreStore` for real-time drift
    detection.

    Args:
        app: The ASGI application.
        log_path: Path to the JSONL log file. Defaults to
            ``/var/lib/tobira/predictions.jsonl``.
        redis_url: Optional Redis connection URL for score accumulation.
        redis_key_prefix: Key prefix for Redis score storage.
        redis_window_seconds: Score retention window in seconds.
    """

    def __init__(
        self,
        app: Any,
        log_path: str = _DEFAULT_LOG_PATH,
        redis_url: str | None = None,
        redis_key_prefix: str = "tobira:scores",
        redis_window_seconds: int = 86400,
    ) -> None:
        self.app = app
        self.log_path = log_path
        self._redis_store: Any = None
        if redis_url:
            try:
                from tobira.monitoring.store import RedisScoreStore

                self._redis_store = RedisScoreStore(
                    redis_url=redis_url,
                    key_prefix=redis_key_prefix,
                    window_seconds=redis_window_seconds,
                )
            except ImportError:
                logger.warning(
                    "redis package not installed; Redis score accumulation disabled"
                )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        is_predict = (
            scope["type"] == "http"
            and scope["path"] == "/predict"
            and scope["method"] == "POST"
        )
        if not is_predict:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0
        body_parts: list[bytes] = []

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if 200 <= status_code < 300:
            self._log_prediction(start, body_parts)

    def _log_prediction(self, start: float, body_parts: list[bytes]) -> None:
        """Parse the response body and write a log record."""
        import json

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        body = b"".join(body_parts)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return

        now = datetime.now(timezone.utc)
        score = data.get("score")
        record: dict[str, object] = {
            "timestamp": now.isoformat(),
            "label": data.get("label"),
            "score": score,
            "latency_ms": latency_ms,
        }
        tenant = data.get("tenant")
        if tenant is not None:
            record["tenant"] = tenant
        append_record(self.log_path, record)

        if self._redis_store is not None and isinstance(score, (int, float)):
            try:
                self._redis_store.push_score(float(score), now.timestamp())
            except Exception:
                logger.debug("Failed to push score to Redis", exc_info=True)
