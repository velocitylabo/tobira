"""Tests for tobira.monitoring.metrics (OpenTelemetry / Prometheus export)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tobira.backends.protocol import BackendProtocol, PredictionResult
from tobira.monitoring.metrics import MetricsConfig, MetricsInstruments

_has_fastapi = True
try:
    from fastapi.testclient import TestClient
except ImportError:
    _has_fastapi = False

_has_otel = True
try:
    from opentelemetry import metrics as otel_metrics  # noqa: F401
except ImportError:
    _has_otel = False

requires_fastapi = pytest.mark.skipif(
    not _has_fastapi, reason="fastapi not installed",
)
requires_otel = pytest.mark.skipif(
    not _has_otel, reason="opentelemetry not installed",
)


def _make_mock_backend() -> MagicMock:
    """Create a mock backend that implements BackendProtocol."""
    backend = MagicMock(spec=BackendProtocol)
    backend.predict.return_value = PredictionResult(
        label="spam", score=0.95, labels={"spam": 0.95, "ham": 0.05},
    )
    return backend


# ── MetricsConfig tests ─────────────────────────────────────────


class TestMetricsConfig:
    def test_defaults(self) -> None:
        cfg = MetricsConfig()
        assert cfg.enabled is False
        assert cfg.prometheus_enabled is True
        assert cfg.otlp_endpoint is None
        assert cfg.otlp_protocol == "http/protobuf"

    def test_from_dict_empty(self) -> None:
        cfg = MetricsConfig.from_dict({})
        assert cfg.enabled is False
        assert cfg.prometheus_enabled is True

    def test_from_dict_enabled(self) -> None:
        cfg = MetricsConfig.from_dict({
            "enabled": True,
            "prometheus_enabled": True,
            "otlp_endpoint": "http://localhost:4318",
            "otlp_protocol": "http/protobuf",
        })
        assert cfg.enabled is True
        assert cfg.otlp_endpoint == "http://localhost:4318"

    def test_from_dict_prometheus_disabled(self) -> None:
        cfg = MetricsConfig.from_dict({
            "enabled": True,
            "prometheus_enabled": False,
        })
        assert cfg.prometheus_enabled is False

    def test_frozen(self) -> None:
        cfg = MetricsConfig()
        with pytest.raises(AttributeError):
            cfg.enabled = True  # type: ignore[misc]


# ── MetricsInstruments tests ────────────────────────────────────


class TestMetricsInstruments:
    def test_default_instruments(self) -> None:
        instruments = MetricsInstruments()
        assert instruments.predict_requests is None
        assert instruments.predict_latency is None
        assert instruments.backend_errors is None
        assert instruments.model_load_duration is None


# ── setup_metrics tests ─────────────────────────────────────────


@requires_otel
class TestSetupMetrics:
    def test_setup_prometheus_only(self) -> None:
        from tobira.monitoring.metrics import setup_metrics

        cfg = MetricsConfig(enabled=True, prometheus_enabled=True)
        instruments = setup_metrics(cfg)

        assert instruments.predict_requests is not None
        assert instruments.predict_latency is not None
        assert instruments.backend_errors is not None
        assert instruments.model_load_duration is not None
        assert instruments._prometheus_reader is not None

    def test_setup_prometheus_disabled(self) -> None:
        from tobira.monitoring.metrics import setup_metrics

        cfg = MetricsConfig(
            enabled=True, prometheus_enabled=False,
        )
        instruments = setup_metrics(cfg)

        assert instruments.predict_requests is not None
        assert instruments._prometheus_reader is None


# ── MetricsMiddleware tests ─────────────────────────────────────


@requires_fastapi
@requires_otel
class TestMetricsMiddleware:
    def _create_app_with_metrics(self) -> TestClient:
        from tobira.serving.server import create_app

        backend = _make_mock_backend()
        app = create_app(
            backend,
            metrics={"enabled": True, "prometheus_enabled": True},
        )
        return TestClient(app)

    def test_predict_records_metrics(self) -> None:
        client = self._create_app_with_metrics()
        resp = client.post("/predict", json={"text": "buy now!!!"})
        assert resp.status_code == 200

    def test_v1_predict_records_metrics(self) -> None:
        client = self._create_app_with_metrics()
        resp = client.post("/v1/predict", json={"text": "buy now!!!"})
        assert resp.status_code == 200

    def test_metrics_endpoint_exists(self) -> None:
        client = self._create_app_with_metrics()
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "tobira_predict" in resp.text or "text/plain" in resp.headers.get(
            "content-type", "",
        )

    def test_metrics_endpoint_after_predict(self) -> None:
        client = self._create_app_with_metrics()
        # Make a prediction first
        client.post("/predict", json={"text": "buy now!!!"})
        # Then check metrics
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "tobira_predict_requests_total" in body

    def test_health_not_affected(self) -> None:
        client = self._create_app_with_metrics()
        resp = client.get("/v1/health")
        assert resp.status_code == 200


@requires_fastapi
class TestMetricsDisabled:
    def test_no_metrics_endpoint_when_disabled(self) -> None:
        from tobira.serving.server import create_app

        backend = _make_mock_backend()
        app = create_app(backend)
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_predict_works_without_metrics(self) -> None:
        from tobira.serving.server import create_app

        backend = _make_mock_backend()
        app = create_app(backend)
        client = TestClient(app)
        resp = client.post("/predict", json={"text": "hello"})
        assert resp.status_code == 200
