"""OpenTelemetry tracing and structured logging for tobira.

Provides distributed tracing across the FastAPI request → backend
inference → response pipeline, and structured JSON logging with
trace context correlation.

All OpenTelemetry dependencies are optional.  When not installed,
a helpful :class:`ImportError` is raised at setup time.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────


@dataclass(frozen=True)
class TracingConfig:
    """Parsed ``[tracing]`` configuration.

    Attributes:
        enabled: Master switch (default ``False``).
        service_name: OpenTelemetry service name.
        otlp_endpoint: OTLP HTTP endpoint URL for trace export.
        console_exporter: Enable console exporter for development.
        sample_rate: Trace sampling rate (0.0 to 1.0).
    """

    enabled: bool = False
    service_name: str = "tobira"
    otlp_endpoint: Optional[str] = None
    console_exporter: bool = False
    sample_rate: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TracingConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            service_name=str(data.get("service_name", "tobira")),
            otlp_endpoint=data.get("otlp_endpoint"),
            console_exporter=bool(data.get("console_exporter", False)),
            sample_rate=float(data.get("sample_rate", 1.0)),
        )


@dataclass(frozen=True)
class StructuredLoggingConfig:
    """Parsed ``[logging]`` configuration.

    Attributes:
        enabled: Master switch (default ``False``).
        format: Log format (``"json"`` or ``"text"``).
        level: Log level name.
        include_trace_id: Embed trace/span IDs in log records.
    """

    enabled: bool = False
    format: str = "json"
    level: str = "INFO"
    include_trace_id: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuredLoggingConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            format=str(data.get("format", "json")),
            level=str(data.get("level", "INFO")).upper(),
            include_trace_id=bool(data.get("include_trace_id", True)),
        )


# ── Lazy imports ─────────────────────────────────────────────────


def _import_otel_trace() -> tuple[Any, ...]:
    """Lazy-import OpenTelemetry tracing packages."""
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:
        raise ImportError(
            "tracing dependencies are not installed. "
            "Install them with: pip install tobira[tracing]"
        ) from None
    return otel_trace, TracerProvider


# ── Tracing setup ────────────────────────────────────────────────


def setup_tracing(config: TracingConfig) -> Any:
    """Initialise OpenTelemetry tracing and return a tracer.

    Args:
        config: Parsed tracing configuration.

    Returns:
        An OpenTelemetry :class:`Tracer` instance.
    """
    otel_trace, TracerProvider = _import_otel_trace()
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": config.service_name})

    exporters: list[Any] = []

    if config.console_exporter:
        try:
            from opentelemetry.sdk.trace.export import (
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )

            exporters.append(SimpleSpanProcessor(ConsoleSpanExporter()))
        except ImportError:
            logger.warning("Console span exporter not available")

    if config.otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            otlp_exporter = OTLPSpanExporter(
                endpoint=config.otlp_endpoint + "/v1/traces",
            )
            exporters.append(BatchSpanProcessor(otlp_exporter))
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-http not installed; "
                "OTLP trace export disabled"
            )

    sampler = None
    if config.sample_rate < 1.0:
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        sampler = TraceIdRatioBased(config.sample_rate)

    provider_kwargs: dict[str, Any] = {"resource": resource}
    if sampler is not None:
        provider_kwargs["sampler"] = sampler

    provider = TracerProvider(**provider_kwargs)
    for proc in exporters:
        provider.add_span_processor(proc)

    otel_trace.set_tracer_provider(provider)

    return otel_trace.get_tracer("tobira", "0.1.0")


def shutdown_tracing() -> None:
    """Flush and shut down the global TracerProvider."""
    try:
        from opentelemetry import trace as otel_trace

        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except Exception:
        pass


# ── Structured logging setup ─────────────────────────────────────


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter with optional trace context."""

    def __init__(self, include_trace_id: bool = True) -> None:
        super().__init__()
        self._include_trace_id = include_trace_id

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_dict: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1] is not None:
            log_dict["exception"] = self.formatException(record.exc_info)

        if self._include_trace_id:
            trace_id = getattr(record, "otelTraceID", "0")
            span_id = getattr(record, "otelSpanID", "0")
            if trace_id != "0":
                log_dict["trace_id"] = trace_id
            if span_id != "0":
                log_dict["span_id"] = span_id

        return json.dumps(log_dict, ensure_ascii=False)


def setup_structured_logging(config: StructuredLoggingConfig) -> None:
    """Configure structured logging for the application.

    Args:
        config: Parsed logging configuration.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level, logging.INFO))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()

    if config.format == "json":
        handler.setFormatter(_JsonFormatter(
            include_trace_id=config.include_trace_id,
        ))
    else:
        fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
        if config.include_trace_id:
            fmt = (
                "%(asctime)s %(levelname)s %(name)s "
                "[trace=%(otelTraceID)s span=%(otelSpanID)s] "
                "%(message)s"
            )
        handler.setFormatter(logging.Formatter(fmt))

    root_logger.addHandler(handler)

    if config.include_trace_id:
        _install_trace_context_filter()


def _install_trace_context_filter() -> None:
    """Add a logging filter that injects OTel trace/span IDs."""

    class _TraceContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            try:
                from opentelemetry import trace as otel_trace

                span = otel_trace.get_current_span()
                ctx = span.get_span_context()
                if ctx and ctx.trace_id:
                    record.otelTraceID = format(ctx.trace_id, "032x")
                    record.otelSpanID = format(ctx.span_id, "016x")
                else:
                    record.otelTraceID = "0"
                    record.otelSpanID = "0"
            except Exception:
                record.otelTraceID = "0"
                record.otelSpanID = "0"
            return True

    logging.getLogger().addFilter(_TraceContextFilter())


# ── ASGI Middleware ───────────────────────────────────────────────


class TracingMiddleware:
    """ASGI middleware that creates spans for incoming HTTP requests.

    Creates a root span for each request with HTTP method, path,
    and status code attributes.  For ``/predict`` endpoints, also
    creates a child span around the backend ``predict()`` call.

    Args:
        app: The ASGI application.
        tracer: An OpenTelemetry :class:`Tracer` instance.
    """

    def __init__(self, app: Any, tracer: Any) -> None:
        self.app = app
        self.tracer = tracer

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        from opentelemetry import trace as otel_trace

        span_name = f"{method} {path}"
        with self.tracer.start_as_current_span(
            span_name,
            kind=otel_trace.SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.target", path)
            span.set_attribute("http.scheme", scope.get("scheme", "http"))

            status_code = 200

            async def send_wrapper(message: dict[str, Any]) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as exc:
                span.set_attribute("error", True)
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("http.status_code", status_code)


def traced_predict(
    backend: Any, text: str, tracer: Any, **kwargs: Any,
) -> Any:
    """Call ``backend.predict()`` wrapped in a tracing span.

    Args:
        backend: A backend instance implementing BackendProtocol.
        text: Input text for prediction.
        tracer: An OpenTelemetry tracer.
        **kwargs: Additional keyword arguments for predict().

    Returns:
        The prediction result from the backend.
    """
    with tracer.start_as_current_span("backend.predict") as span:
        span.set_attribute("tobira.text_length", len(text))
        span.set_attribute("tobira.backend", type(backend).__name__)

        start = time.monotonic()
        try:
            try:
                result = backend.predict(text, **kwargs)
            except TypeError:
                result = backend.predict(text)
        except Exception as exc:
            span.set_attribute("error", True)
            span.record_exception(exc)
            raise

        elapsed = time.monotonic() - start
        span.set_attribute("tobira.latency_ms", round(elapsed * 1000, 2))
        span.set_attribute("tobira.label", result.label)
        span.set_attribute("tobira.score", result.score)

        return result
