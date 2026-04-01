"""Audit logging for the tobira API.

Records all API operations (authentication, prediction requests, config
changes) as structured JSON events. Supports JSONL file output and the
pluggable :class:`~tobira.monitoring.store.StoreProtocol` backends.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from tobira.monitoring.store import JsonlStore, StoreProtocol

logger = logging.getLogger(__name__)

_AUDIT_COLLECTION = "audit"


@dataclass(frozen=True)
class AuditEvent:
    """A single audit log entry.

    Attributes:
        timestamp: ISO-8601 UTC timestamp.
        user: Identifier of the authenticated user (key name or ``"anonymous"``).
        role: Role of the user (or ``"none"``).
        action: Operation performed (e.g. ``"predict"``, ``"auth_failure"``).
        resource: API resource accessed (e.g. ``"/v1/predict"``).
        status: Outcome — ``"allowed"``, ``"denied"``, or ``"error"``.
        detail: Additional context (e.g. reason for denial).
        ip_address: Client IP address.
        latency_ms: Request latency in milliseconds (if applicable).
    """

    timestamp: str
    user: str
    role: str
    action: str
    resource: str
    status: str
    detail: str = ""
    ip_address: str = ""
    latency_ms: float | None = None


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Writes :class:`AuditEvent` records to a :class:`StoreProtocol` backend.

    Args:
        store: Storage backend for audit records.
        collection: Collection name within the store.
    """

    def __init__(
        self,
        store: StoreProtocol,
        collection: str = _AUDIT_COLLECTION,
    ) -> None:
        self._store = store
        self._collection = collection

    def log(self, event: AuditEvent) -> None:
        """Persist an audit event.

        Errors during storage are logged but never propagated — audit
        logging must not break request handling.
        """
        try:
            self._store.append(self._collection, asdict(event))
        except Exception:
            logger.exception("Failed to write audit event")

    def read_events(
        self,
        last_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read audit events from the store.

        Args:
            last_n: If given, return only the most recent *last_n* events.

        Returns:
            List of audit event dicts, oldest first.
        """
        records = self._store.read_all(self._collection)
        if last_n is not None and last_n > 0:
            records = records[-last_n:]
        return records


@dataclass
class AuditConfig:
    """Audit logging configuration.

    Attributes:
        enabled: Whether audit logging is active.
        log_path: Path to the JSONL audit log file.
        retention_days: How many days of logs to retain (informational).
    """

    enabled: bool = False
    log_path: str = "/var/lib/tobira/audit.jsonl"
    retention_days: int = 90


def load_audit_config(config: dict[str, Any] | None) -> AuditConfig:
    """Build an :class:`AuditConfig` from the ``[audit]`` TOML section.

    Args:
        config: The ``[audit]`` dict from the TOML config, or ``None``.

    Returns:
        A populated :class:`AuditConfig`.
    """
    if not config:
        return AuditConfig()
    return AuditConfig(
        enabled=bool(config.get("enabled", False)),
        log_path=config.get("log_path", "/var/lib/tobira/audit.jsonl"),
        retention_days=int(config.get("retention_days", 90)),
    )


def create_audit_logger(config: AuditConfig) -> AuditLogger | None:
    """Create an :class:`AuditLogger` from config, or ``None`` if disabled.

    Args:
        config: Audit configuration.

    Returns:
        An :class:`AuditLogger` instance, or ``None``.
    """
    if not config.enabled:
        return None
    from pathlib import Path

    base_dir = str(Path(config.log_path).parent)
    store = JsonlStore(base_dir=base_dir)
    collection = Path(config.log_path).stem
    return AuditLogger(store=store, collection=collection)


class AuditMiddleware:
    """ASGI middleware that records audit events for every request.

    Captures user identity (from ``request.state.authenticated_user``),
    request path, method, response status, and latency.

    Args:
        app: The ASGI application.
        audit_logger: The :class:`AuditLogger` to write events to.
    """

    def __init__(self, app: Any, audit_logger: AuditLogger) -> None:
        self.app = app
        self.audit_logger = audit_logger

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        latency_ms = (time.monotonic() - start) * 1000.0

        path = scope.get("path", "")
        method = scope.get("method", "")

        # Skip health endpoints to reduce noise
        if path.rstrip("/").endswith(("/health", "/health/ready", "/health/live")):
            return

        # Extract user from request state (set by auth dependency)
        user = "anonymous"
        role = "none"
        state = scope.get("state", {})
        auth_user = state.get("authenticated_user")
        if auth_user is not None:
            user = auth_user.key_name
            role = auth_user.role.value

        # Determine action from path
        action = _action_from_path(path, method)

        # Determine status
        if status_code == 401:
            status = "denied"
            detail = "authentication required"
        elif status_code == 403:
            status = "denied"
            detail = "insufficient permissions"
        elif 400 <= status_code < 500:
            status = "error"
            detail = f"client error {status_code}"
        elif status_code >= 500:
            status = "error"
            detail = f"server error {status_code}"
        else:
            status = "allowed"
            detail = ""

        # Extract client IP
        client = scope.get("client")
        ip_address = client[0] if client else ""

        event = AuditEvent(
            timestamp=_now_iso(),
            user=user,
            role=role,
            action=action,
            resource=f"{method} {path}",
            status=status,
            detail=detail,
            ip_address=ip_address,
            latency_ms=round(latency_ms, 2),
        )
        self.audit_logger.log(event)


def _action_from_path(path: str, method: str) -> str:
    """Derive a human-readable action name from the request path."""
    clean = path.rstrip("/")
    if clean.endswith("/predict"):
        return "predict"
    if clean.endswith("/feedback"):
        return "feedback"
    if "/active-learning" in clean:
        return "active_learning"
    if "/dashboard" in clean:
        return "view_dashboard"
    if "/ab-test" in clean:
        return "ab_test"
    return f"{method.lower()}:{clean}"
