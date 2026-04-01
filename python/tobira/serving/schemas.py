"""Pydantic request/response models for the serving API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_TEXT_LENGTH = 102_400  # 100 KB


class EmailHeaders(BaseModel):
    """Email header fields for header-based classification."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "from": "sender@example.com",
                    "reply_to": "different@example.com",
                    "spf": "fail",
                    "dkim": "none",
                    "received": ["from mx1.example.com by mx2.example.com"],
                },
            ],
        },
    )

    spf: str | None = Field(
        default=None,
        description="SPF verification result (pass, fail, softfail, none).",
    )
    dkim: str | None = Field(
        default=None,
        description="DKIM verification result (pass, fail, none).",
    )
    dmarc: str | None = Field(
        default=None,
        description="DMARC policy result (pass, fail, none).",
    )
    from_addr: str | None = Field(
        default=None,
        alias="from",
        description="From header address.",
    )
    reply_to: str | None = Field(
        default=None,
        description="Reply-To header address.",
    )
    received: list[str] | None = Field(
        default=None,
        description="List of Received header values.",
    )
    content_type: str | None = Field(
        default=None,
        description="Content-Type header value.",
    )


class PredictRequest(BaseModel):
    """Request body for POST /predict."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"text": "Buy now! Limited offer!!!"},
                {"text": "お買い得！今すぐ購入！", "language": "ja"},
                {
                    "text": "Buy now!",
                    "headers": {
                        "from": "sender@example.com",
                        "reply_to": "different@example.com",
                        "spf": "fail",
                        "dkim": "none",
                    },
                },
            ],
        },
    )

    text: str = Field(..., max_length=MAX_TEXT_LENGTH)
    headers: EmailHeaders | None = Field(
        default=None,
        description="Optional email headers for header-based classification. "
        "When provided, header features are analyzed and combined "
        "with the text classification score.",
    )
    language: str | None = Field(
        default=None,
        description="ISO 639-1 language code (e.g. 'ja', 'en', 'ko'). "
        "When omitted, language is auto-detected.",
    )
    explain: bool = Field(
        default=False,
        description="When true, include token-level attribution scores "
        "in the response (supported backends only).",
    )


class TokenAttributionInfo(BaseModel):
    """Token-level attribution score for explainability."""

    token: str
    score: float = Field(description="Attribution score (0.0-1.0).")


class AIGeneratedInfo(BaseModel):
    """AI-generated text detection result embedded in prediction responses."""

    detected: bool
    confidence: float
    indicators: list[str] = Field(default_factory=list)


class PredictResponse(BaseModel):
    """Response body for POST /predict."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "label": "spam",
                    "score": 0.95,
                    "labels": {"spam": 0.95, "ham": 0.05},
                    "language": "en",
                },
                {
                    "label": "phishing",
                    "score": 0.82,
                    "labels": {
                        "ham": 0.05,
                        "phishing": 0.82,
                        "malware": 0.03,
                        "financial_fraud": 0.04,
                        "lottery": 0.01,
                        "romance_scam": 0.01,
                        "drug": 0.02,
                        "fake_service": 0.01,
                        "tech_support": 0.01,
                    },
                },
                {
                    "label": "spam",
                    "score": 0.92,
                    "labels": {"spam": 0.92, "ham": 0.08},
                    "language": "en",
                    "ai_generated": {
                        "detected": True,
                        "confidence": 0.85,
                        "indicators": [
                            "low_entropy",
                            "uniform_vocabulary",
                        ],
                    },
                },
            ],
        },
    )

    label: str
    score: float
    labels: dict[str, float]
    header_score: float | None = Field(
        default=None,
        description="Header-based spam risk score (0.0-1.0). "
        "Only present when headers were provided in the request.",
    )
    language: str | None = Field(
        default=None,
        description="Detected or specified language code.",
    )
    ai_generated: AIGeneratedInfo | None = Field(
        default=None,
        description="AI-generated text detection result. "
        "Present only when ai_detection is enabled in server config.",
    )
    explanations: list[TokenAttributionInfo] | None = Field(
        default=None,
        description="Token-level attribution scores. "
        "Present only when explain=true in the request and "
        "the backend supports explainability.",
    )
    model_version: str | None = Field(
        default=None,
        description="A/B test variant name that served this prediction. "
        "Present only when ab_test is enabled in server config.",
    )
    tenant: str | None = Field(
        default=None,
        description="Tenant identifier that served this prediction. "
        "Present only when multi-tenancy is enabled in server config.",
    )


class FeedbackRequest(BaseModel):
    """Request body for POST /feedback."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "Buy now! Limited offer!!!",
                    "label": "spam",
                    "source": "rspamd",
                },
            ],
        },
    )

    text: str = Field(..., max_length=MAX_TEXT_LENGTH)
    label: str = Field(..., pattern=r"^(spam|ham)$")
    source: str = Field(default="unknown", max_length=256)


class FeedbackResponse(BaseModel):
    """Response body for POST /feedback."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "accepted", "id": "feedback-uuid"},
            ],
        },
    )

    status: str
    id: str


class DashboardFeedbackRequest(BaseModel):
    """Request body for POST /api/feedback (dashboard feedback)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "Buy now! Limited offer!!!",
                    "correct_label": "ham",
                    "source": "dashboard",
                },
            ],
        },
    )

    text: str = Field(..., max_length=MAX_TEXT_LENGTH)
    correct_label: str = Field(..., pattern=r"^(spam|ham)$")
    source: str = Field(default="dashboard", max_length=256)


class FeedbackStatsResponse(BaseModel):
    """Response body for GET /api/feedback/stats."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 10,
                    "spam_reports": 7,
                    "ham_reports": 3,
                },
            ],
        },
    )

    total: int
    spam_reports: int
    ham_reports: int


class ABTestVariantResult(BaseModel):
    """Result summary for a single A/B test variant."""

    predictions: int
    avg_latency_ms: float
    avg_score: float
    label_counts: dict[str, int]
    errors: int


class ABTestResultsResponse(BaseModel):
    """Response body for GET /api/ab-test/results."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "variants": {
                        "control": {
                            "predictions": 800,
                            "avg_latency_ms": 12.5,
                            "avg_score": 0.85,
                            "label_counts": {"spam": 600, "ham": 200},
                            "errors": 0,
                        },
                        "candidate": {
                            "predictions": 200,
                            "avg_latency_ms": 15.3,
                            "avg_score": 0.87,
                            "label_counts": {"spam": 155, "ham": 45},
                            "errors": 1,
                        },
                    },
                },
            ],
        },
    )

    variants: dict[str, ABTestVariantResult]


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok"},
                {"status": "ok", "telemetry_enabled": True},
            ],
        },
    )

    status: str
    telemetry_enabled: bool | None = Field(
        default=None,
        description="Whether opt-in anonymous telemetry is enabled. "
        "Present only when the [telemetry] section exists in config.",
    )


class ReadinessResponse(BaseModel):
    """Response body for GET /health/ready (readiness probe)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"ready": True},
                {"ready": False, "reason": "model loading"},
            ],
        },
    )

    ready: bool
    reason: str | None = Field(
        default=None,
        description="Reason when not ready (e.g. 'model loading', 'shutting down').",
    )


class LivenessResponse(BaseModel):
    """Response body for GET /health/live (liveness probe)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"alive": True}],
        },
    )

    alive: bool


class ActiveLearningSampleResponse(BaseModel):
    """A single Active Learning candidate sample."""

    id: str
    text: str
    score: float
    labels: dict[str, float]
    uncertainty: float
    strategy: str
    timestamp: str
    labeled: bool
    assigned_label: str | None = None


class ActiveLearningQueueResponse(BaseModel):
    """Response body for GET /active-learning/queue."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "samples": [
                        {
                            "id": "abc-123",
                            "text": "Check this offer...",
                            "score": 0.55,
                            "labels": {"spam": 0.55, "ham": 0.45},
                            "uncertainty": 0.99,
                            "strategy": "entropy",
                            "timestamp": "2025-01-01T00:00:00+00:00",
                            "labeled": False,
                            "assigned_label": None,
                        },
                    ],
                    "total": 1,
                    "pending": 1,
                    "labeled": 0,
                },
            ],
        },
    )

    samples: list[ActiveLearningSampleResponse]
    total: int
    pending: int
    labeled: int


class ActiveLearningLabelRequest(BaseModel):
    """Request body for POST /active-learning/label."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"sample_id": "abc-123", "label": "spam"},
            ],
        },
    )

    sample_id: str
    label: str = Field(..., pattern=r"^(spam|ham)$")


class ActiveLearningLabelResponse(BaseModel):
    """Response body for POST /active-learning/label."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "labeled", "sample_id": "abc-123", "label": "spam"},
            ],
        },
    )

    status: str
    sample_id: str
    label: str


class ActiveLearningStatsResponse(BaseModel):
    """Response body for GET /active-learning/stats."""

    total: int
    pending: int
    labeled: int
    label_counts: dict[str, int]


class TenantInfoResponse(BaseModel):
    """Information about a single tenant."""

    tenant_id: str = Field(description="Unique tenant identifier.")
    display_name: str = Field(default="", description="Human-readable name.")


class TenantListResponse(BaseModel):
    """Response body for GET /v1/tenants."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tenants": [
                        {"tenant_id": "org-a", "display_name": "Organization A"},
                        {"tenant_id": "org-b", "display_name": "Organization B"},
                    ],
                    "total": 2,
                },
            ],
        },
    )

    tenants: list[TenantInfoResponse]
    total: int


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details error response.

    All API error responses use this schema, providing a machine-readable
    ``code`` for programmatic handling and a human-readable ``detail`` for
    debugging.

    See https://datatracker.ietf.org/doc/html/rfc7807
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "Service Not Ready",
                    "status": 503,
                    "detail": "The backend model is still loading.",
                    "code": "SERVING_NOT_READY",
                },
                {
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": "Sample abc-123 not found.",
                    "code": "SERVING_NOT_FOUND",
                },
            ],
        },
    )

    type: str = Field(
        default="about:blank",
        description="A URI reference identifying the problem type.",
    )
    title: str = Field(
        description="A short, human-readable summary of the problem type.",
    )
    status: int = Field(
        description="The HTTP status code.",
    )
    detail: str = Field(
        description="A human-readable explanation specific to this occurrence.",
    )
    code: str = Field(
        description="A machine-readable tobira error code (e.g. SERVING_NOT_READY).",
    )
