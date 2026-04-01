"""Tests for tobira.serving.audit — Audit logging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tobira.backends.protocol import BackendProtocol, PredictionResult
from tobira.serving.audit import (
    AuditConfig,
    AuditEvent,
    AuditLogger,
    _action_from_path,
    _now_iso,
    create_audit_logger,
    load_audit_config,
)

_has_fastapi = True
try:
    from fastapi.testclient import TestClient
except ImportError:
    _has_fastapi = False

requires_fastapi = pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")

ADMIN_KEY = "admin-secret-key-1234567890"


def _make_mock_backend() -> MagicMock:
    backend = MagicMock(spec=BackendProtocol)
    backend.predict.return_value = PredictionResult(
        label="spam", score=0.95, labels={"spam": 0.95, "ham": 0.05}
    )
    return backend


def _make_rbac_config() -> dict:
    return {
        "enabled": True,
        "api_keys": [
            {"key": ADMIN_KEY, "name": "admin-user", "role": "admin"},
        ],
    }


class TestAuditEvent:
    def test_frozen_dataclass(self) -> None:
        event = AuditEvent(
            timestamp="2024-01-01T00:00:00+00:00",
            user="test-user",
            role="admin",
            action="predict",
            resource="POST /v1/predict",
            status="allowed",
        )
        assert event.user == "test-user"
        with pytest.raises(AttributeError):
            event.user = "other"  # type: ignore[misc]


class TestLoadAuditConfig:
    def test_none_returns_defaults(self) -> None:
        cfg = load_audit_config(None)
        assert not cfg.enabled
        assert cfg.retention_days == 90

    def test_enabled_config(self) -> None:
        cfg = load_audit_config({
            "enabled": True,
            "log_path": "/tmp/audit.jsonl",
            "retention_days": 30,
        })
        assert cfg.enabled
        assert cfg.log_path == "/tmp/audit.jsonl"
        assert cfg.retention_days == 30


class TestCreateAuditLogger:
    def test_disabled_returns_none(self) -> None:
        assert create_audit_logger(AuditConfig(enabled=False)) is None

    def test_enabled_returns_logger(self, tmp_path: Path) -> None:
        cfg = AuditConfig(
            enabled=True,
            log_path=str(tmp_path / "audit.jsonl"),
        )
        logger = create_audit_logger(cfg)
        assert logger is not None


class TestAuditLogger:
    def test_log_and_read(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")

        event = AuditEvent(
            timestamp=_now_iso(),
            user="test-user",
            role="admin",
            action="predict",
            resource="POST /v1/predict",
            status="allowed",
            ip_address="127.0.0.1",
            latency_ms=42.5,
        )
        logger.log(event)

        events = logger.read_events()
        assert len(events) == 1
        assert events[0]["user"] == "test-user"
        assert events[0]["action"] == "predict"
        assert events[0]["latency_ms"] == 42.5

    def test_read_last_n(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")

        for i in range(5):
            logger.log(AuditEvent(
                timestamp=_now_iso(),
                user=f"user-{i}",
                role="admin",
                action="predict",
                resource="POST /v1/predict",
                status="allowed",
            ))

        events = logger.read_events(last_n=2)
        assert len(events) == 2
        assert events[0]["user"] == "user-3"
        assert events[1]["user"] == "user-4"

    def test_store_error_is_swallowed(self) -> None:
        store = MagicMock()
        store.append.side_effect = RuntimeError("disk full")
        logger = AuditLogger(store=store, collection="audit")

        event = AuditEvent(
            timestamp=_now_iso(),
            user="test",
            role="admin",
            action="predict",
            resource="POST /v1/predict",
            status="allowed",
        )
        # Should not raise
        logger.log(event)


class TestActionFromPath:
    def test_predict(self) -> None:
        assert _action_from_path("/v1/predict", "POST") == "predict"

    def test_feedback(self) -> None:
        assert _action_from_path("/v1/feedback", "POST") == "feedback"

    def test_active_learning(self) -> None:
        assert _action_from_path("/active-learning/queue", "GET") == "active_learning"

    def test_dashboard(self) -> None:
        assert _action_from_path("/dashboard/stats", "GET") == "view_dashboard"

    def test_unknown_path(self) -> None:
        assert _action_from_path("/v1/custom", "GET") == "get:/v1/custom"


@requires_fastapi
class TestAuditMiddleware:
    def test_audit_events_are_recorded(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore
        from tobira.serving.server import create_app

        log_path = str(tmp_path / "audit.jsonl")
        app = create_app(
            _make_mock_backend(),
            audit={"enabled": True, "log_path": log_path},
        )
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 200

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")
        events = logger.read_events()
        assert len(events) >= 1

        predict_events = [e for e in events if e["action"] == "predict"]
        assert len(predict_events) == 1
        assert predict_events[0]["status"] == "allowed"

    def test_health_not_audited(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore
        from tobira.serving.server import create_app

        log_path = str(tmp_path / "audit.jsonl")
        app = create_app(
            _make_mock_backend(),
            audit={"enabled": True, "log_path": log_path},
        )
        client = TestClient(app)

        client.get("/v1/health")

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")
        events = logger.read_events()
        health_events = [e for e in events if "health" in e.get("resource", "")]
        assert len(health_events) == 0

    def test_denied_request_is_audited(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore
        from tobira.serving.server import create_app

        log_path = str(tmp_path / "audit.jsonl")
        app = create_app(
            _make_mock_backend(),
            rbac=_make_rbac_config(),
            audit={"enabled": True, "log_path": log_path},
        )
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 401

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")
        events = logger.read_events()

        denied_events = [e for e in events if e["status"] == "denied"]
        assert len(denied_events) >= 1

    def test_authenticated_user_recorded(self, tmp_path: Path) -> None:
        from tobira.monitoring.store import JsonlStore
        from tobira.serving.server import create_app

        log_path = str(tmp_path / "audit.jsonl")
        app = create_app(
            _make_mock_backend(),
            rbac=_make_rbac_config(),
            audit={"enabled": True, "log_path": log_path},
        )
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        assert resp.status_code == 200

        store = JsonlStore(base_dir=str(tmp_path))
        logger = AuditLogger(store=store, collection="audit")
        events = logger.read_events()

        predict_events = [e for e in events if e["action"] == "predict"]
        assert len(predict_events) == 1
        assert predict_events[0]["user"] == "admin-user"
        assert predict_events[0]["role"] == "admin"


class TestAuditLogCli:
    def test_audit_log_subcommand_exists(self) -> None:
        from tobira.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["audit-log", "--config", "test.toml", "--last", "5"])
        assert args.command == "audit-log"
        assert args.last == 5
