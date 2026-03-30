"""Mock tobira API server for integration testing.

Returns deterministic predictions based on keywords in the input text.
Implements all documented API endpoints for comprehensive hands-on testing.
No ML model required.
"""

import hashlib
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="tobira-mock")

# ---------------------------------------------------------------------------
# In-memory stores (reset on restart)
# ---------------------------------------------------------------------------
_feedback_store: list[dict] = []
_al_queue: list[dict] = [
    {
        "id": "al-001",
        "text": "Exclusive membership offer just for you - act now!",
        "uncertainty": 0.92,
        "strategy": "entropy",
        "created_at": "2026-03-28T10:00:00Z",
        "label": None,
    },
    {
        "id": "al-002",
        "text": "Your invoice #4821 is attached. Please review.",
        "uncertainty": 0.85,
        "strategy": "entropy",
        "created_at": "2026-03-28T10:05:00Z",
        "label": None,
    },
    {
        "id": "al-003",
        "text": "Congratulations! You may have been selected for a reward.",
        "uncertainty": 0.78,
        "strategy": "entropy",
        "created_at": "2026-03-28T10:10:00Z",
        "label": None,
    },
]
_ab_start = time.time()
_predict_count = 0


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class HeadersInput(BaseModel):
    spf: str | None = None
    dkim: str | None = None
    dmarc: str | None = None
    from_addr: str | None = None
    reply_to: str | None = None
    received: list[str] | None = None
    content_type: str | None = None


class PredictRequest(BaseModel):
    text: str
    headers: HeadersInput | None = None
    language: str | None = None
    explain: bool = False


class PredictResponse(BaseModel):
    label: str
    score: float
    labels: dict[str, float]
    header_score: float | None = None
    language: str | None = None
    ai_generated: dict | None = None
    explanations: list[dict] | None = None
    model_version: str = "mock-1.0"


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    ready: bool
    reason: str | None = None


class LivenessResponse(BaseModel):
    alive: bool


class FeedbackRequest(BaseModel):
    text: str
    label: str
    source: str | None = "user"


class FeedbackResponse(BaseModel):
    status: str
    id: str


class ActiveLearningLabelRequest(BaseModel):
    id: str
    label: str


# ---------------------------------------------------------------------------
# Spam classifier (rule-based)
# ---------------------------------------------------------------------------
SPAM_PATTERNS = re.compile(
    r"(buy now|free offer|click here|viagra|lottery|winner|"
    r"urgent|act now|limited time|casino|cheap|discount)",
    re.IGNORECASE,
)

AI_PATTERNS = re.compile(
    r"(as an ai|in conclusion|it.s important to note|"
    r"delve into|comprehensive overview|facilitate)",
    re.IGNORECASE,
)


def _classify(req: PredictRequest) -> PredictResponse:
    """Rule-based classifier with support for all response fields."""
    text = req.text
    matches = len(SPAM_PATTERNS.findall(text))

    if matches >= 3:
        spam_score = 0.95
    elif matches == 2:
        spam_score = 0.80
    elif matches == 1:
        spam_score = 0.60
    else:
        h = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        spam_score = (h % 20) / 100.0

    ham_score = round(1.0 - spam_score, 4)
    label = "spam" if spam_score >= 0.5 else "ham"
    score = spam_score if label == "spam" else ham_score

    # Header analysis
    header_score = None
    if req.headers:
        risk = 0.0
        h = req.headers
        if h.spf and h.spf.lower() not in ("pass",):
            risk += 0.15
        if h.dkim and h.dkim.lower() not in ("pass",):
            risk += 0.15
        if h.dmarc and h.dmarc.lower() not in ("pass",):
            risk += 0.20
        if h.from_addr and h.reply_to and h.from_addr != h.reply_to:
            risk += 0.10
        header_score = round(min(risk, 1.0), 2)

    # Language detection (mock)
    detected_lang = req.language
    if not detected_lang:
        if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
            detected_lang = "ja"
        else:
            detected_lang = "en"

    # AI-generated text detection (mock)
    ai_matches = len(AI_PATTERNS.findall(text))
    ai_generated = {
        "is_ai_generated": ai_matches >= 2,
        "confidence": min(0.3 * ai_matches, 0.99),
    }

    # Explanations
    explanations = None
    if req.explain:
        found = SPAM_PATTERNS.findall(text)
        explanations = []
        if found:
            for kw in found[:5]:
                explanations.append(
                    {"token": kw.lower(), "attribution": 0.15, "type": "keyword_match"}
                )
        else:
            explanations.append(
                {"token": "(no spam keywords)", "attribution": 0.0, "type": "absence"}
            )
        if header_score and header_score > 0:
            explanations.append(
                {
                    "token": "header_risk",
                    "attribution": header_score,
                    "type": "header_analysis",
                }
            )

    return PredictResponse(
        label=label,
        score=score,
        labels={"spam": spam_score, "ham": ham_score},
        header_score=header_score,
        language=detected_lang,
        ai_generated=ai_generated,
        explanations=explanations,
        model_version="mock-1.0",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/v1/predict", response_model=PredictResponse)
async def predict(req: PredictRequest) -> PredictResponse:
    global _predict_count
    _predict_count += 1
    return _classify(req)


@app.get("/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/v1/health/ready", response_model=ReadinessResponse)
async def health_ready() -> ReadinessResponse:
    return ReadinessResponse(ready=True)


@app.get("/v1/health/live", response_model=LivenessResponse)
async def health_live() -> LivenessResponse:
    return LivenessResponse(alive=True)


# --- Feedback ---


@app.post("/v1/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    entry_id = f"fb-{uuid.uuid4().hex[:8]}"
    _feedback_store.append(
        {
            "id": entry_id,
            "text": req.text[:200],
            "label": req.label,
            "source": req.source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return FeedbackResponse(status="accepted", id=entry_id)


# --- Active Learning ---


@app.get("/v1/active-learning/queue")
async def al_queue():
    pending = [item for item in _al_queue if item["label"] is None]
    labeled = [item for item in _al_queue if item["label"] is not None]
    return {
        "items": sorted(pending, key=lambda x: -x["uncertainty"]),
        "total": len(_al_queue),
        "pending": len(pending),
        "labeled": len(labeled),
    }


@app.post("/v1/active-learning/label")
async def al_label(req: ActiveLearningLabelRequest):
    for item in _al_queue:
        if item["id"] == req.id:
            item["label"] = req.label
            return {"status": "labeled", "id": req.id, "label": req.label}
    return {"status": "not_found", "id": req.id}


@app.get("/v1/active-learning/stats")
async def al_stats():
    pending = sum(1 for i in _al_queue if i["label"] is None)
    labeled = sum(1 for i in _al_queue if i["label"] is not None)
    return {
        "total": len(_al_queue),
        "pending": pending,
        "labeled": labeled,
        "strategy": "entropy",
        "avg_uncertainty": round(
            sum(i["uncertainty"] for i in _al_queue if i["label"] is None)
            / max(pending, 1),
            4,
        ),
    }


# --- A/B Testing ---


@app.get("/api/ab-test/results")
async def ab_test_results():
    elapsed = time.time() - _ab_start
    return {
        "variants": {
            "control": {
                "predictions": max(_predict_count // 2, 1),
                "avg_latency_ms": 12.3,
                "avg_score": 0.42,
                "label_counts": {"spam": max(_predict_count // 4, 0), "ham": max(_predict_count // 4, 1)},
                "errors": 0,
            },
            "challenger": {
                "predictions": max(_predict_count - _predict_count // 2, 1),
                "avg_latency_ms": 45.7,
                "avg_score": 0.44,
                "label_counts": {"spam": max((_predict_count - _predict_count // 2) // 2, 0), "ham": max((_predict_count - _predict_count // 2) // 2, 1)},
                "errors": 0,
            },
        },
        "started_at": datetime.fromtimestamp(_ab_start, tz=timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 1),
    }


# --- Dashboard ---


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    pending = sum(1 for i in _al_queue if i["label"] is None)
    labeled = sum(1 for i in _al_queue if i["label"] is not None)
    fb_count = len(_feedback_store)
    return f"""<!DOCTYPE html>
<html><head><title>tobira Dashboard (mock)</title>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 2em auto; }}
.card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1em; margin: 1em 0; }}
h1 {{ color: #333; }}
.metric {{ font-size: 2em; font-weight: bold; color: #2563eb; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em; }}
</style></head><body>
<h1>tobira Dashboard (mock mode)</h1>
<div class="grid">
  <div class="card"><div>Total Predictions</div><div class="metric">{_predict_count}</div></div>
  <div class="card"><div>Feedback Reports</div><div class="metric">{fb_count}</div></div>
  <div class="card"><div>Active Learning Queue</div><div class="metric">{pending} pending / {labeled} labeled</div></div>
</div>
<p style="color:#888; margin-top:2em;">This is a mock dashboard for hands-on testing.
In production, the real dashboard includes prediction trends, latency graphs, and drift detection.</p>
</body></html>"""
