"""OpenTelemetry / Prometheus metrics export for tobira.

Provides an ASGI middleware that records prediction request metrics
(count, latency, errors) using the OpenTelemetry SDK and exposes them
via a Prometheus ``/metrics`` endpoint.  Optionally, metrics can be
pushed to an OpenTelemetry Collector over OTLP HTTP.

All OpenTelemetry and Prometheus dependencies are optional.  When not
installed, a helpful :class:`ImportError` is raised at setup time.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricsConfig:
    """Parsed ``[metrics]`` configuration.

    Attributes:
        enabled: Master switch (default ``False``).
        prometheus_enabled: Serve ``/metrics`` Prometheus endpoint.
        otlp_endpoint: OTLP HTTP endpoint URL (e.g.
            ``http://localhost:4318``).  When set, metrics are pushed
            via OTLP in addition to the Prometheus endpoint.
        otlp_protocol: OTLP transport protocol.
    """

    enabled: bool = False
    prometheus_enabled: bool = True
    otlp_endpoint: str | None = None
    otlp_protocol: str = "http/protobuf"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricsConfig:
        """Create a :class:`MetricsConfig` from a configuration dict.

        Args:
            data: Configuration dictionary (typically the ``[metrics]``
                section of ``tobira.toml``).

        Returns:
            A :class:`MetricsConfig` instance.
        """
        return cls(
            enabled=bool(data.get("enabled", False)),
            prometheus_enabled=bool(data.get("prometheus_enabled", True)),
            otlp_endpoint=data.get("otlp_endpoint"),
            otlp_protocol=str(data.get("otlp_protocol", "http/protobuf")),
        )


# ── Instruments container ────────────────────────────────────────


@dataclass
class MetricsInstruments:
    """Holds references to OpenTelemetry metric instruments.

    Created once by :func:`setup_metrics` and shared via ``app.state``.
    """

    predict_requests: Any = field(default=None)
    predict_latency: Any = field(default=None)
    backend_errors: Any = field(default=None)
    model_load_duration: Any = field(default=None)
    _prometheus_reader: Any = field(default=None, repr=False)


# ── Setup ────────────────────────────────────────────────────────


def _import_otel() -> tuple[Any, ...]:
    """Lazy-import OpenTelemetry packages."""
    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry.sdk.metrics import MeterProvider
    except ImportError:
        raise ImportError(
            "metrics dependencies are not installed. "
            "Install them with: pip install tobira[metrics]"
        ) from None
    return otel_metrics, MeterProvider


def setup_metrics(config: MetricsConfig) -> MetricsInstruments:
    """Initialise OpenTelemetry metrics and return instrument handles.

    Args:
        config: Parsed metrics configuration.

    Returns:
        A :class:`MetricsInstruments` instance with counters, histograms,
        and (optionally) a Prometheus reader for serving ``/metrics``.
    """
    otel_metrics, MeterProvider = _import_otel()

    readers: list[Any] = []
    prometheus_reader = None

    # Prometheus MetricReader
    if config.prometheus_enabled:
        try:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader

            prometheus_reader = PrometheusMetricReader()
            readers.append(prometheus_reader)
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-prometheus not installed; "
                "Prometheus /metrics endpoint disabled"
            )

    # OTLP HTTP exporter
    if config.otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import (
                PeriodicExportingMetricReader,
            )

            otlp_exporter = OTLPMetricExporter(endpoint=config.otlp_endpoint)
            readers.append(PeriodicExportingMetricReader(otlp_exporter))
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-http not installed; "
                "OTLP export disabled"
            )

    provider = MeterProvider(metric_readers=readers)
    otel_metrics.set_meter_provider(provider)

    meter = provider.get_meter("tobira", "0.1.0")

    predict_requests = meter.create_counter(
        name="tobira_predict_requests_total",
        description="Total number of prediction requests",
        unit="1",
    )

    predict_latency = meter.create_histogram(
        name="tobira_predict_latency_seconds",
        description="Prediction request latency",
        unit="s",
    )

    backend_errors = meter.create_counter(
        name="tobira_backend_errors_total",
        description="Total number of backend errors",
        unit="1",
    )

    model_load_duration = meter.create_histogram(
        name="tobira_model_load_duration_seconds",
        description="Time taken to load the model",
        unit="s",
    )

    return MetricsInstruments(
        predict_requests=predict_requests,
        predict_latency=predict_latency,
        backend_errors=backend_errors,
        model_load_duration=model_load_duration,
        _prometheus_reader=prometheus_reader,
    )


# ── Prometheus endpoint ──────────────────────────────────────────


def create_metrics_endpoint(instruments: MetricsInstruments) -> Any:
    """Create a Starlette ``/metrics`` route handler.

    Args:
        instruments: The metrics instruments (must have a Prometheus reader).

    Returns:
        An async callable suitable for use with ``app.add_api_route``.
    """

    async def metrics_endpoint() -> Any:
        from starlette.responses import Response

        try:
            from prometheus_client import (
                CONTENT_TYPE_LATEST,
                generate_latest,
            )
        except ImportError:
            return Response(
                content="prometheus_client not installed",
                status_code=501,
            )
        data = generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return metrics_endpoint


# ── ASGI Middleware ───────────────────────────────────────────────


class MetricsMiddleware:
    """Starlette middleware that records prediction metrics.

    Intercepts ``POST /predict`` (and ``POST /v1/predict``) requests
    and records request count, latency, and error count via
    OpenTelemetry instruments.

    Args:
        app: The ASGI application.
        instruments: :class:`MetricsInstruments` from :func:`setup_metrics`.
    """

    def __init__(self, app: Any, instruments: MetricsInstruments) -> None:
        self.app = app
        self.instruments = instruments

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any,
    ) -> None:
        path = scope.get("path", "")
        is_predict = (
            scope["type"] == "http"
            and path in ("/predict", "/v1/predict")
            and scope["method"] == "POST"
        )
        if not is_predict:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if self.instruments.backend_errors is not None:
                self.instruments.backend_errors.add(1)
            raise

        elapsed = time.monotonic() - start
        attrs: dict[str, str] = {"path": path}

        if self.instruments.predict_requests is not None:
            self.instruments.predict_requests.add(
                1, {**attrs, "status": str(status_code)},
            )

        if self.instruments.predict_latency is not None:
            self.instruments.predict_latency.record(elapsed, attrs)

        if status_code >= 500 and self.instruments.backend_errors is not None:
            self.instruments.backend_errors.add(1, attrs)
