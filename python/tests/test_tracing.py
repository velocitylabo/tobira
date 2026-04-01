"""Tests for tobira.tracing."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest

from tobira.tracing import (
    StructuredLoggingConfig,
    TracingConfig,
    _JsonFormatter,
    setup_structured_logging,
    traced_predict,
)

_has_fastapi = True
try:
    from fastapi.testclient import TestClient
except ImportError:
    _has_fastapi = False

_has_otel = True
try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ReadableSpan,
        SimpleSpanProcessor,
        SpanExporter,
        SpanExportResult,
    )
except ImportError:
    _has_otel = False

requires_fastapi = pytest.mark.skipif(
    not _has_fastapi, reason="fastapi not installed",
)
requires_otel = pytest.mark.skipif(
    not _has_otel, reason="opentelemetry not installed",
)


class _CollectingExporter(SpanExporter if _has_otel else object):  # type: ignore[misc]
    """Simple span exporter that collects spans in a list."""

    def __init__(self) -> None:
        self.spans: list[Any] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:  # type: ignore[override]
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# ── TracingConfig ────────────────────────────────────────────────


class TestTracingConfig:
    def test_defaults(self) -> None:
        cfg = TracingConfig()
        assert cfg.enabled is False
        assert cfg.service_name == "tobira"
        assert cfg.otlp_endpoint is None
        assert cfg.console_exporter is False
        assert cfg.sample_rate == 1.0

    def test_from_dict_empty(self) -> None:
        cfg = TracingConfig.from_dict({})
        assert cfg.enabled is False

    def test_from_dict_full(self) -> None:
        cfg = TracingConfig.from_dict({
            "enabled": True,
            "service_name": "my-tobira",
            "otlp_endpoint": "http://localhost:4318",
            "console_exporter": True,
            "sample_rate": 0.5,
        })
        assert cfg.enabled is True
        assert cfg.service_name == "my-tobira"
        assert cfg.otlp_endpoint == "http://localhost:4318"
        assert cfg.console_exporter is True
        assert cfg.sample_rate == 0.5


# ── StructuredLoggingConfig ──────────────────────────────────────


class TestStructuredLoggingConfig:
    def test_defaults(self) -> None:
        cfg = StructuredLoggingConfig()
        assert cfg.enabled is False
        assert cfg.format == "json"
        assert cfg.level == "INFO"
        assert cfg.include_trace_id is True

    def test_from_dict_empty(self) -> None:
        cfg = StructuredLoggingConfig.from_dict({})
        assert cfg.enabled is False

    def test_from_dict_full(self) -> None:
        cfg = StructuredLoggingConfig.from_dict({
            "enabled": True,
            "format": "text",
            "level": "debug",
            "include_trace_id": False,
        })
        assert cfg.enabled is True
        assert cfg.format == "text"
        assert cfg.level == "DEBUG"
        assert cfg.include_trace_id is False


# ── JSON Formatter ───────────────────────────────────────────────


class TestJsonFormatter:
    def test_basic_format(self) -> None:
        formatter = _JsonFormatter(include_trace_id=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "hello world"
        assert "trace_id" not in parsed

    def test_format_with_trace_id_defaults(self) -> None:
        formatter = _JsonFormatter(include_trace_id=True)
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="warn msg", args=(), exc_info=None,
        )
        record.otelTraceID = "abc123"  # type: ignore[attr-defined]
        record.otelSpanID = "def456"  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "abc123"
        assert parsed["span_id"] == "def456"

    def test_format_zero_trace_id_excluded(self) -> None:
        formatter = _JsonFormatter(include_trace_id=True)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        record.otelTraceID = "0"  # type: ignore[attr-defined]
        record.otelSpanID = "0"  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "trace_id" not in parsed
        assert "span_id" not in parsed


# ── Structured Logging Setup ─────────────────────────────────────


class TestSetupStructuredLogging:
    def test_json_logging(self) -> None:
        cfg = StructuredLoggingConfig(
            enabled=True, format="json", level="DEBUG",
            include_trace_id=False,
        )
        setup_structured_logging(cfg)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, _JsonFormatter)
        # Cleanup
        root.handlers.clear()
        root.filters.clear()

    def test_text_logging(self) -> None:
        cfg = StructuredLoggingConfig(
            enabled=True, format="text", level="WARNING",
            include_trace_id=False,
        )
        setup_structured_logging(cfg)
        root = logging.getLogger()
        assert root.level == logging.WARNING
        # Cleanup
        root.handlers.clear()
        root.filters.clear()


# ── Tracing Setup ────────────────────────────────────────────────


@requires_otel
class TestSetupTracing:
    def test_setup_returns_tracer(self) -> None:
        from tobira.tracing import setup_tracing

        cfg = TracingConfig(enabled=True, service_name="test-tobira")
        tracer = setup_tracing(cfg)
        assert tracer is not None
        # Cleanup
        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()

    def test_setup_with_sampling(self) -> None:
        from tobira.tracing import setup_tracing

        cfg = TracingConfig(enabled=True, sample_rate=0.1)
        tracer = setup_tracing(cfg)
        assert tracer is not None
        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()


# ── traced_predict ───────────────────────────────────────────────


@requires_otel
class TestTracedPredict:
    def _make_provider(self) -> tuple[Any, Any]:
        exporter = _CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        otel_trace.set_tracer_provider(provider)
        tracer = provider.get_tracer("test")
        return tracer, exporter

    def test_traced_predict_creates_span(self) -> None:
        tracer, exporter = self._make_provider()

        @dataclass(frozen=True)
        class FakeResult:
            label: str = "ham"
            score: float = 0.1
            labels: dict[str, float] = None  # type: ignore[assignment]
            explanations: None = None

            def __post_init__(self) -> None:
                if self.labels is None:
                    object.__setattr__(self, "labels", {"ham": 0.9, "spam": 0.1})

        backend = MagicMock()
        backend.predict.return_value = FakeResult()

        result = traced_predict(backend, "test text", tracer)
        assert result.label == "ham"

        assert len(exporter.spans) == 1
        span = exporter.spans[0]
        assert span.name == "backend.predict"
        attrs = dict(span.attributes or {})
        assert attrs["tobira.text_length"] == 9
        assert attrs["tobira.label"] == "ham"
        assert attrs["tobira.score"] == 0.1
        assert "tobira.latency_ms" in attrs

        otel_trace.get_tracer_provider().shutdown()  # type: ignore[union-attr]

    def test_traced_predict_records_error(self) -> None:
        tracer, exporter = self._make_provider()

        backend = MagicMock()
        backend.predict.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            traced_predict(backend, "fail", tracer)

        assert len(exporter.spans) == 1
        attrs = dict(exporter.spans[0].attributes or {})
        assert attrs.get("error") is True

        otel_trace.get_tracer_provider().shutdown()  # type: ignore[union-attr]


# ── TracingMiddleware ────────────────────────────────────────────


@requires_fastapi
@requires_otel
class TestTracingMiddleware:
    def test_middleware_creates_span_on_request(self) -> None:
        from tobira.backends.protocol import BackendProtocol, PredictionResult
        from tobira.serving.server import create_app
        from tobira.tracing import TracingMiddleware

        exporter = _CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        backend = MagicMock(spec=BackendProtocol)
        backend.predict.return_value = PredictionResult(
            label="ham", score=0.1, labels={"ham": 0.9, "spam": 0.1},
        )
        # Create app without tracing, then manually add middleware
        app = create_app(backend)
        app.add_middleware(TracingMiddleware, tracer=tracer)
        app.state.tracer = tracer

        client = TestClient(app)
        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 200

        span_names = [s.name for s in exporter.spans]
        assert any(
            "predict" in name.lower() or "POST" in name
            for name in span_names
        )

        provider.shutdown()

    def test_app_works_without_tracing(self) -> None:
        from tobira.backends.protocol import BackendProtocol, PredictionResult
        from tobira.serving.server import create_app

        backend = MagicMock(spec=BackendProtocol)
        backend.predict.return_value = PredictionResult(
            label="spam", score=0.9, labels={"ham": 0.1, "spam": 0.9},
        )
        app = create_app(backend)

        client = TestClient(app)
        resp = client.post("/v1/predict", json={"text": "buy now"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "spam"
