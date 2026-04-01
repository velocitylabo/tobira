"""FastAPI application for spam prediction."""

from typing import Any, Optional

from tobira.backends.factory import create_backend
from tobira.backends.protocol import BackendProtocol
from tobira.config import load_toml
from tobira.errors import (
    SERVING_NOT_FOUND,
    SERVING_NOT_READY,
)


def _import_deps() -> tuple[Any, Any]:
    """Lazy-import FastAPI and uvicorn."""
    try:
        import fastapi
        import uvicorn
    except ImportError:
        raise ImportError(
            "serving dependencies are not installed. "
            "Install them with: pip install tobira[serving]"
        ) from None
    return fastapi, uvicorn


def _make_error_response(
    status_code: int, title: str, detail: str, code: str,
) -> dict[str, Any]:
    """Build an RFC 7807 Problem Details dict."""
    return {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
    }


def create_app(
    backend: BackendProtocol,
    monitoring: Optional[dict[str, Any]] = None,
    feedback: Optional[dict[str, Any]] = None,
    header_analysis: Optional[dict[str, Any]] = None,
    dashboard: Optional[dict[str, Any]] = None,
    ai_detection: Optional[dict[str, Any]] = None,
    ab_test: Optional[dict[str, Any]] = None,
    active_learning: Optional[dict[str, Any]] = None,
    telemetry: Optional[dict[str, Any]] = None,
    serving: Optional[dict[str, Any]] = None,
    metrics: Optional[dict[str, Any]] = None,
    tenant_registry: Optional[Any] = None,
    tracing: Optional[dict[str, Any]] = None,
    structured_logging: Optional[dict[str, Any]] = None,
) -> Any:
    """Create a FastAPI application with the given backend.

    Args:
        backend: A backend instance implementing BackendProtocol.
        monitoring: Optional monitoring configuration dict.
            When ``{"enabled": true}`` is set, prediction metrics are logged
            to a JSONL file. Accepts an optional ``log_path`` key.
        feedback: Optional feedback configuration dict.
            When ``{"enabled": true}`` is set, the ``POST /feedback``
            endpoint is registered. Accepts an optional ``store_path`` key.
        header_analysis: Optional header analysis configuration dict.
            When ``{"enabled": true}`` is set, header features are analyzed
            and combined with text classification scores. Accepts optional
            ``weight`` (float, 0.0-1.0) for blending ratio and ``weights``
            (dict) for per-feature weights.
        dashboard: Optional dashboard configuration dict.
            When ``{"enabled": true}`` is set, the web dashboard is served
            at ``/dashboard`` with stats API endpoints.
        ai_detection: Optional AI-generated text detection configuration.
            When ``{"enabled": true}`` is set, each prediction response
            includes an ``ai_generated`` field. Accepts an optional
            ``threshold`` key (default 0.65).
        ab_test: Optional A/B test configuration dict.
            When ``{"enabled": true}`` is set, requests are routed across
            configured variants. Accepts ``variants`` (list) and optional
            ``strategy`` (``"random"`` or ``"hash"``).
        active_learning: Optional Active Learning configuration dict.
            When ``{"enabled": true}`` is set, Active Learning endpoints
            (``/active-learning/queue``, ``/active-learning/label``,
            ``/active-learning/stats``) are registered. Accepts optional
            ``strategy``, ``uncertainty_threshold``, ``max_queue_size``,
            and ``queue_path`` keys.
        telemetry: Optional telemetry configuration dict.
            When ``{"enabled": true}`` is set, the ``/health`` endpoint
            includes ``telemetry_enabled`` in its response and heartbeats
            are recorded locally.
        serving: Optional serving configuration dict.
            When ``api_key`` is set (or ``TOBIRA_API_KEY`` environment
            variable is present), Bearer token authentication is enforced
            on ``/predict``, ``/feedback``, and active-learning endpoints.
            Health endpoints remain unauthenticated.
        metrics: Optional metrics configuration dict.
            When ``{"enabled": true}`` is set, OpenTelemetry metrics are
            collected for prediction requests and a Prometheus ``/metrics``
            endpoint is registered.  Accepts optional
            ``prometheus_enabled`` (bool), ``otlp_endpoint`` (str), and
            ``otlp_protocol`` (str) keys.
        tenant_registry: Optional :class:`TenantRegistry` instance.
            When provided, multi-tenant mode is enabled: requests must
            include an ``X-Tobira-Tenant`` header to select the tenant,
            and each tenant uses its own backend and isolated data stores.
        tracing: Optional tracing configuration dict.
            When ``{"enabled": true}`` is set, OpenTelemetry tracing
            is enabled for HTTP requests and backend predict calls.
        structured_logging: Optional structured logging configuration.
            When ``{"enabled": true}`` is set, logs are output in
            structured JSON format with trace context correlation.

    Returns:
        A FastAPI application.
    """
    fastapi, _ = _import_deps()

    import tobira
    from tobira.serving.ha import ReadinessState
    from tobira.serving.schemas import (
        AIGeneratedInfo,
        ErrorResponse,
        HealthResponse,
        LivenessResponse,
        PredictRequest,
        PredictResponse,
        ReadinessResponse,
        TokenAttributionInfo,
    )

    ai_detector = None
    if ai_detection and ai_detection.get("enabled"):
        from tobira.adversarial.ai_generated import AIGeneratedDetector

        threshold = ai_detection.get("threshold", 0.65)
        ai_detector = AIGeneratedDetector(threshold=threshold)

    telemetry_collector = None
    telemetry_enabled: Optional[bool] = None
    if telemetry is not None:
        from tobira.telemetry import TelemetryCollector, TelemetryConfig

        tel_cfg = TelemetryConfig.from_dict(telemetry)
        telemetry_enabled = tel_cfg.enabled
        if tel_cfg.enabled:
            telemetry_collector = TelemetryCollector(tel_cfg)

    tracer = None
    if structured_logging and structured_logging.get("enabled"):
        from tobira.tracing import StructuredLoggingConfig, setup_structured_logging

        sl_cfg = StructuredLoggingConfig.from_dict(structured_logging)
        setup_structured_logging(sl_cfg)

    if tracing and tracing.get("enabled"):
        from tobira.tracing import TracingConfig, setup_tracing

        tr_cfg = TracingConfig.from_dict(tracing)
        tracer = setup_tracing(tr_cfg)

    from tobira.serving.auth import get_api_key

    api_key = get_api_key(serving)
    auth_deps: list[Any] = []
    if api_key:
        from tobira.serving.auth import create_auth_dependency

        auth_deps = [fastapi.Depends(create_auth_dependency(api_key))]

    # Multi-tenant support: dependency that resolves tenant_id from header
    _tenant_dep: Any = None
    if tenant_registry is not None:
        from tobira.serving.tenant import create_tenant_dependency

        _tenant_dep = create_tenant_dependency(tenant_registry)
        auth_deps.append(fastapi.Depends(_tenant_dep))

    # Helper dependency: optional tenant_id from header (for endpoint DI)
    _TENANT_HEADER_NAME = "X-Tobira-Tenant"

    async def _get_optional_tenant_id(
        tenant_id: str = fastapi.Header(
            default=None, alias=_TENANT_HEADER_NAME,
        ),
    ) -> Optional[str]:
        return tenant_id

    readiness = ReadinessState()

    app = fastapi.FastAPI(
        title="tobira",
        description="Spam prediction API powered by tobira.",
        version=tobira.__version__,
    )
    app.state.backend = backend
    app.state.header_analysis = header_analysis
    app.state.readiness = readiness

    from fastapi.exceptions import RequestValidationError
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Return validation errors in RFC 7807 format."""
        from tobira.errors import SERVING_VALIDATION_ERROR

        return JSONResponse(
            status_code=422,
            content=_make_error_response(
                422,
                "Validation Error",
                str(exc),
                SERVING_VALIDATION_ERROR,
            ),
        )

    # Backend is already loaded at this point, so mark as ready.
    # During shutdown, GracefulShutdown sets this back to False.
    readiness.set_ready()

    ab_router = None
    if ab_test and ab_test.get("enabled"):
        from tobira.serving.ab_test import create_ab_router

        ab_router = create_ab_router(ab_test)
    app.state.ab_router = ab_router

    if monitoring and monitoring.get("enabled"):
        from tobira.monitoring.collector import PredictionCollector

        log_path = monitoring.get("log_path", "/var/lib/tobira/predictions.jsonl")
        redis_url = monitoring.get("redis_url")
        redis_key_prefix = monitoring.get("redis_key_prefix", "tobira:scores")
        redis_window = monitoring.get("redis_window_seconds", 86400)
        app.add_middleware(
            PredictionCollector,
            log_path=log_path,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
            redis_window_seconds=redis_window,
        )

    if metrics and metrics.get("enabled"):
        from tobira.monitoring.metrics import (
            MetricsConfig,
            MetricsMiddleware,
            create_metrics_endpoint,
            setup_metrics,
        )

        metrics_cfg = MetricsConfig.from_dict(metrics)
        instruments = setup_metrics(metrics_cfg)
        app.state.metrics_instruments = instruments
        app.add_middleware(MetricsMiddleware, instruments=instruments)

        prom_reader = instruments._prometheus_reader
        if metrics_cfg.prometheus_enabled and prom_reader is not None:
            metrics_handler = create_metrics_endpoint(instruments)
            app.add_api_route(
                "/metrics", metrics_handler, methods=["GET"], tags=["metrics"],
            )

    if tracer is not None:
        from tobira.tracing import TracingMiddleware

        app.add_middleware(TracingMiddleware, tracer=tracer)
    app.state.tracer = tracer

    # --- Versioned router (v1) ---
    v1_router = fastapi.APIRouter(prefix="/v1", tags=["v1"])

    # --- Protected router (v1, requires auth when api_key is set) ---
    v1_protected = fastapi.APIRouter(
        prefix="/v1", tags=["v1"], dependencies=auth_deps,
    )

    if feedback and feedback.get("enabled"):
        from tobira.data.feedback_store import DEFAULT_FEEDBACK_PATH, store_feedback
        from tobira.serving.schemas import FeedbackRequest, FeedbackResponse

        feedback_path = feedback.get("store_path", DEFAULT_FEEDBACK_PATH)

        @v1_protected.post(
            "/feedback", response_model=FeedbackResponse, tags=["feedback"]
        )
        async def receive_feedback(
            req: FeedbackRequest,
            tenant_id: Optional[str] = fastapi.Depends(_get_optional_tenant_id),
        ) -> FeedbackResponse:
            path = feedback_path
            if tenant_registry is not None and tenant_id:
                from pathlib import Path as _Path

                base = _Path(feedback_path).parent
                path = str(base / f"feedback_{tenant_id}.jsonl")
            record = store_feedback(
                req.text, req.label, req.source, path=path
            )
            return FeedbackResponse(status="accepted", id=record.id)

    if dashboard and dashboard.get("enabled"):
        from tobira.serving.dashboard import register_dashboard_routes

        log_path = "/var/lib/tobira/predictions.jsonl"
        if monitoring and monitoring.get("log_path"):
            log_path = monitoring["log_path"]
        if dashboard.get("log_path"):
            log_path = dashboard["log_path"]

        dash_feedback_path: Optional[str] = None
        if feedback and feedback.get("enabled"):
            from tobira.data.feedback_store import DEFAULT_FEEDBACK_PATH

            dash_feedback_path = feedback.get("store_path", DEFAULT_FEEDBACK_PATH)
        register_dashboard_routes(
            app, log_path=log_path, feedback_path=dash_feedback_path,
        )

    if ab_router is not None:
        from tobira.serving.ab_test import register_ab_test_routes

        register_ab_test_routes(app, ab_router)

    if active_learning and active_learning.get("enabled"):
        from tobira.evaluation.active_learning import UncertaintySampler
        from tobira.serving.schemas import (
            ActiveLearningLabelRequest,
            ActiveLearningLabelResponse,
            ActiveLearningQueueResponse,
            ActiveLearningSampleResponse,
            ActiveLearningStatsResponse,
        )

        sampler = UncertaintySampler(
            strategy=active_learning.get("strategy", "entropy"),
            uncertainty_threshold=active_learning.get(
                "uncertainty_threshold", 0.3
            ),
            max_queue_size=active_learning.get("max_queue_size", 1000),
            queue_path=active_learning.get(
                "queue_path", "/var/lib/tobira/active_learning_queue.jsonl"
            ),
        )
        app.state.active_learning_sampler = sampler

        @app.get(
            "/active-learning/queue",
            response_model=ActiveLearningQueueResponse,
            tags=["active-learning"],
            dependencies=auth_deps,
        )
        async def al_queue() -> ActiveLearningQueueResponse:
            pending = sampler.get_pending()
            stats = sampler.queue_stats()
            return ActiveLearningQueueResponse(
                samples=[
                    ActiveLearningSampleResponse(
                        id=s.id,
                        text=s.text,
                        score=s.score,
                        labels=s.labels,
                        uncertainty=s.uncertainty,
                        strategy=s.strategy,
                        timestamp=s.timestamp,
                        labeled=s.labeled,
                        assigned_label=s.assigned_label,
                    )
                    for s in pending
                ],
                total=stats["total"],
                pending=stats["pending"],
                labeled=stats["labeled"],
            )

        @app.post(
            "/active-learning/label",
            response_model=ActiveLearningLabelResponse,
            tags=["active-learning"],
            dependencies=auth_deps,
        )
        async def al_label(
            req: ActiveLearningLabelRequest,
        ) -> ActiveLearningLabelResponse:
            updated = sampler.label_sample(req.sample_id, req.label)
            if updated is None:
                raise fastapi.HTTPException(
                    status_code=404,
                    detail=_make_error_response(
                        404,
                        "Not Found",
                        f"Sample {req.sample_id!r} not found "
                        "in the active learning queue.",
                        SERVING_NOT_FOUND,
                    ),
                )
            return ActiveLearningLabelResponse(
                status="labeled",
                sample_id=req.sample_id,
                label=req.label,
            )

        @app.get(
            "/active-learning/stats",
            response_model=ActiveLearningStatsResponse,
            tags=["active-learning"],
            dependencies=auth_deps,
        )
        async def al_stats() -> ActiveLearningStatsResponse:
            stats = sampler.queue_stats()
            return ActiveLearningStatsResponse(**stats)

    @v1_protected.post(
        "/predict",
        response_model=PredictResponse,
        responses={503: {"model": ErrorResponse}},
        tags=["prediction"],
    )
    async def predict(
        req: PredictRequest,
        tenant_id: Optional[str] = fastapi.Depends(_get_optional_tenant_id),
    ) -> PredictResponse:
        if not readiness.ready:
            raise fastapi.HTTPException(
                status_code=503,
                detail=_make_error_response(
                    503,
                    "Service Not Ready",
                    "The backend model is still loading.",
                    SERVING_NOT_READY,
                ),
            )
        variant_name: Optional[str] = None
        explain_kwargs: dict[str, bool] = {}
        if req.explain:
            explain_kwargs["explain"] = True

        # Resolve backend: tenant-specific or default
        current_backend = app.state.backend
        if tenant_registry is not None and tenant_id:
            tenant_backend = tenant_registry.get_backend(tenant_id)
            if tenant_backend is not None:
                current_backend = tenant_backend

        if app.state.ab_router is not None:
            result, variant_name = app.state.ab_router.predict(req.text)
        elif app.state.tracer is not None:
            from tobira.tracing import traced_predict

            result = traced_predict(
                app.state.backend, req.text, app.state.tracer,
                **explain_kwargs,
            )
        else:
            try:
                result = current_backend.predict(req.text, **explain_kwargs)
            except TypeError:
                # Backend does not support explain parameter
                result = current_backend.predict(req.text)

        header_score: Optional[float] = None
        final_score = result.score
        final_labels = dict(result.labels)

        ha_config = app.state.header_analysis
        if req.headers is not None and ha_config and ha_config.get("enabled"):
            from tobira.preprocessing.headers import analyze_headers

            header_dict: dict[str, object] = {}
            if req.headers.spf is not None:
                header_dict["spf"] = req.headers.spf
            if req.headers.dkim is not None:
                header_dict["dkim"] = req.headers.dkim
            if req.headers.dmarc is not None:
                header_dict["dmarc"] = req.headers.dmarc
            if req.headers.from_addr is not None:
                header_dict["from"] = req.headers.from_addr
            if req.headers.reply_to is not None:
                header_dict["reply_to"] = req.headers.reply_to
            if req.headers.received is not None:
                header_dict["received"] = req.headers.received
            if req.headers.content_type is not None:
                header_dict["content_type"] = req.headers.content_type

            feature_weights = ha_config.get("weights")
            header_score = analyze_headers(header_dict, feature_weights)

            blend_weight = ha_config.get("weight", 0.3)
            text_weight = 1.0 - blend_weight
            final_score = text_weight * result.score + blend_weight * header_score
            # Adjust the spam label score proportionally
            if "spam" in final_labels:
                final_labels["spam"] = (
                    text_weight * final_labels["spam"]
                    + blend_weight * header_score
                )
            if "ham" in final_labels:
                final_labels["ham"] = (
                    text_weight * final_labels["ham"]
                    + blend_weight * (1.0 - header_score)
                )

        language = req.language
        if language is None:
            try:
                from tobira.preprocessing.language import detect_language

                lang_result = detect_language(req.text)
                language = lang_result.language
            except (ImportError, ValueError):
                pass

        final_label = result.label
        if final_labels:
            final_label = max(final_labels, key=lambda k: final_labels[k])
        ai_generated = None
        if ai_detector is not None:
            ai_result = ai_detector.detect(req.text)
            ai_generated = AIGeneratedInfo(
                detected=ai_result.detected,
                confidence=ai_result.confidence,
                indicators=ai_result.indicators,
            )

        explanations_info: Optional[list[TokenAttributionInfo]] = None
        if result.explanations is not None:
            explanations_info = [
                TokenAttributionInfo(token=a.token, score=a.score)
                for a in result.explanations
            ]

        tenant_name: Optional[str] = None
        if tenant_registry is not None:
            tenant_name = tenant_id

        return PredictResponse(
            label=final_label,
            score=final_score,
            labels=final_labels,
            header_score=header_score,
            language=language,
            ai_generated=ai_generated,
            explanations=explanations_info,
            model_version=variant_name,
            tenant=tenant_name,
        )

    @v1_router.get(
        "/health",
        response_model=HealthResponse,
        response_model_exclude_none=True,
        tags=["health"],
    )
    async def health() -> HealthResponse:
        if telemetry_collector is not None:
            backend_name = type(backend).__name__
            try:
                telemetry_collector.record_heartbeat(backend_name)
            except Exception:
                pass  # telemetry must never break health checks
        return HealthResponse(
            status="ok",
            telemetry_enabled=telemetry_enabled,
        )

    @v1_router.get(
        "/health/ready", response_model=ReadinessResponse, tags=["health"]
    )
    async def health_ready() -> ReadinessResponse:
        if readiness.ready:
            return ReadinessResponse(ready=True)
        reason = (
            "shutting down"
            if getattr(app.state, "_shutting_down", False)
            else "model loading"
        )
        return ReadinessResponse(ready=False, reason=reason)

    @v1_router.get(
        "/health/live", response_model=LivenessResponse, tags=["health"]
    )
    async def health_live() -> LivenessResponse:
        return LivenessResponse(alive=True)

    # Tenant list endpoint (unauthenticated, read-only)
    if tenant_registry is not None:
        from tobira.serving.schemas import TenantInfoResponse, TenantListResponse

        @v1_router.get(
            "/tenants",
            response_model=TenantListResponse,
            tags=["tenants"],
        )
        async def list_tenants() -> TenantListResponse:
            tenants = tenant_registry.list_tenants()
            return TenantListResponse(
                tenants=[
                    TenantInfoResponse(
                        tenant_id=t.tenant_id,
                        display_name=t.display_name,
                    )
                    for t in tenants
                ],
                total=len(tenants),
            )

    app.include_router(v1_router)
    app.include_router(v1_protected)

    # --- Legacy unversioned routes (aliases to v1 for backward compatibility) ---
    app.post(
        "/predict",
        response_model=PredictResponse,
        tags=["prediction"],
        dependencies=auth_deps,
    )(predict)
    app.get(
        "/health",
        response_model=HealthResponse,
        response_model_exclude_none=True,
        tags=["health"],
    )(health)
    app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])(
        health_ready
    )
    app.get("/health/live", response_model=LivenessResponse, tags=["health"])(
        health_live
    )
    if feedback and feedback.get("enabled"):
        app.post(
            "/feedback",
            response_model=FeedbackResponse,
            tags=["feedback"],
            dependencies=auth_deps,
        )(receive_feedback)

    return app


def main(config_path: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the server from a TOML config file.

    Supports graceful shutdown: on SIGTERM/SIGINT, the readiness probe
    returns ``False`` so that load balancers stop routing new traffic,
    then the server drains in-flight requests before exiting.

    Args:
        config_path: Path to the TOML configuration file.
        host: Host to bind to.
        port: Port to bind to.
    """
    _, uvicorn = _import_deps()

    config = load_toml(config_path)
    backend_config = config["backend"]
    backend = create_backend(backend_config)
    monitoring_config = config.get("monitoring")

    feedback_config = config.get("feedback")
    header_analysis_config = config.get("header_analysis")
    dashboard_config = config.get("dashboard")
    ai_detection_config = config.get("ai_detection")
    ab_test_config = config.get("ab_test")
    active_learning_config = config.get("active_learning")
    telemetry_config = config.get("telemetry")
    serving_config = config.get("serving")
    metrics_config = config.get("metrics")
    tracing_config = config.get("tracing")
    logging_config = config.get("logging")

    # Multi-tenant setup
    registry = None
    from tobira.serving.tenant import TenantRegistry, load_tenant_configs

    tenant_configs = load_tenant_configs(config)
    if tenant_configs:
        registry = TenantRegistry()
        for tc in tenant_configs:
            registry.register(tc)

    app = create_app(
        backend,
        monitoring=monitoring_config,
        feedback=feedback_config,
        header_analysis=header_analysis_config,
        dashboard=dashboard_config,
        ai_detection=ai_detection_config,
        ab_test=ab_test_config,
        active_learning=active_learning_config,
        telemetry=telemetry_config,
        serving=serving_config,
        metrics=metrics_config,
        tenant_registry=registry,
        tracing=tracing_config,
        structured_logging=logging_config,
    )

    ha_config = config.get("ha", {})
    drain_seconds = ha_config.get("drain_seconds", 5.0)

    from tobira.serving.ha import GracefulShutdown

    shutdown = GracefulShutdown(
        readiness=app.state.readiness,
        drain_seconds=drain_seconds,
    )
    shutdown.install()

    try:
        uvicorn.run(app, host=host, port=port, access_log=False)
    finally:
        if tracing_config and tracing_config.get("enabled"):
            from tobira.tracing import shutdown_tracing

            shutdown_tracing()
