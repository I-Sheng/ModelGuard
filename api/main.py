"""
ModelGuard AI - Batch Model Theft Detection API
Partners submit query logs; ModelGuard detects model extraction campaigns.
MinIO stores: the Isolation Forest detector model, batch audit logs, theft reports.
"""

import io
import json
import logging
import os
import pickle
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import numpy as np
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt as _bcrypt
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, ConfigDict, Field
from sklearn.ensemble import IsolationForest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("modelguard")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="ModelGuard AI",
    description="Batch model theft detection — analyze partner query logs for extraction campaigns",
    version="0.3.0-oss",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth — JWT + role-based access control
# Roles: "analyst" (read-only), "partner" (submit batches + own audits), "admin" (all)
# ---------------------------------------------------------------------------
JWT_SECRET         = os.getenv("JWT_SECRET_KEY", "modelguard-dev-secret-change-in-production")
JWT_ALGORITHM      = "HS256"
JWT_EXPIRE_MINUTES = 60

_USERS: dict[str, dict] = {
    "analyst1": {"password": os.getenv("ANALYST1_PASSWORD", "analyst_password"), "role": "analyst"},
    "partner1": {"password": os.getenv("PARTNER1_PASSWORD", "partner_password"), "role": "partner"},
    "admin":    {"password": os.getenv("ADMIN_PASSWORD",    "admin_password"),   "role": "admin"},
}
_HASHED_USERS = {
    u: {"hashed_password": _bcrypt.hashpw(v["password"].encode(), _bcrypt.gensalt()), "role": v["role"]}
    for u, v in _USERS.items()
}


def _create_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "role": role, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if not username or not role:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"username": username, "role": role}


def require_role(*roles: str):
    """Return a FastAPI dependency that enforces the given role(s)."""
    async def _check(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check


_ANY_AUTHED = require_role("analyst", "partner", "admin")
_PARTNER    = require_role("partner", "admin")

# ---------------------------------------------------------------------------
# MinIO client
# ---------------------------------------------------------------------------
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

BUCKET_DETECTORS = "modelguard-detectors"
BUCKET_AUDITLOG  = "modelguard-auditlog"
BUCKET_REPORTS   = "modelguard-reports"

DETECTOR_KEY = "v1/detector.pkl"

minio_client: Optional[Minio] = None


def get_minio() -> Minio:
    global minio_client
    if minio_client is None:
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return minio_client


def ensure_buckets() -> None:
    mc = get_minio()
    for bucket in [BUCKET_DETECTORS, BUCKET_AUDITLOG, BUCKET_REPORTS]:
        if not mc.bucket_exists(bucket):
            mc.make_bucket(bucket)
            logger.info("Created bucket: %s", bucket)


# ---------------------------------------------------------------------------
# Isolation Forest detector
# Feature vector per user (5-dim):
#   [query_count, unique_input_ratio, avg_input_length, input_entropy, output_diversity]
# ---------------------------------------------------------------------------
_detector: Optional[IsolationForest] = None

_NORMAL_SEED = np.random.default_rng(42)
_TRAIN_DATA  = np.clip(
    _NORMAL_SEED.normal(
        loc=[30.0, 0.60, 100.0, 3.5, 0.45],
        scale=[10.0, 0.10,  40.0, 0.4, 0.10],
        size=(500, 5),
    ),
    [1.0, 0.0, 1.0, 0.0, 0.0],
    None,
)


def _save_detector(clf: IsolationForest) -> None:
    mc = get_minio()
    data = pickle.dumps(clf)
    mc.put_object(
        BUCKET_DETECTORS, DETECTOR_KEY,
        io.BytesIO(data), length=len(data),
        content_type="application/octet-stream",
    )
    logger.info("Detector saved to MinIO: %s/%s", BUCKET_DETECTORS, DETECTOR_KEY)


def _load_detector_from_minio() -> Optional[IsolationForest]:
    mc = get_minio()
    try:
        response = mc.get_object(BUCKET_DETECTORS, DETECTOR_KEY)
        clf = pickle.loads(response.read())
        logger.info("Detector loaded from MinIO: %s/%s", BUCKET_DETECTORS, DETECTOR_KEY)
        return clf
    except S3Error:
        return None


def get_detector() -> IsolationForest:
    global _detector
    if _detector is None:
        _detector = _load_detector_from_minio()
        if _detector is None:
            _detector = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
            _detector.fit(_TRAIN_DATA)
            logger.info("Isolation Forest trained on %d synthetic samples.", len(_TRAIN_DATA))
            try:
                _save_detector(_detector)
            except Exception as exc:
                logger.warning("Could not persist detector to MinIO: %s", exc)
    return _detector


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRecord(BaseModel):
    query_id:   str
    query_user: str
    input:      str
    output:     str


class BatchAnalyzeRequest(BaseModel):
    partner_id:   str = Field(..., description="Partner identifier (AI company submitting the batch)")
    window_start: str = Field(..., description="ISO 8601 start of the query window")
    window_end:   str = Field(..., description="ISO 8601 end of the query window")
    queries: list[QueryRecord] = Field(
        ..., description="Query records in the window", max_length=100_000
    )


class UserRiskResult(BaseModel):
    query_user:  str
    query_count: int
    risk_score:  float
    risk_level:  str
    anomaly:     bool
    features:    dict


class BatchAnalyzeResponse(BaseModel):
    batch_id:         str
    partner_id:       str
    window_start:     str
    window_end:       str
    total_queries:    int
    total_users:      int
    flagged_users:    int
    batch_risk_level: str
    user_results:     list[UserRiskResult]
    timestamp:        str
    audit_log_key:    str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class HealthResponse(BaseModel):
    status:    str
    minio:     str
    detector:  str
    frontend:  str
    timestamp: str


class StatsResponse(BaseModel):
    total_partners:         int
    total_batches_analyzed: int
    detector:               str
    minio:                  str
    timestamp:              str


class PartnerActivityItem(BaseModel):
    partner_id:             str
    total_batches:          int
    last_seen:              str
    hours_since_last_batch: float


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    freq: dict = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * np.log2(c / n) for c in freq.values())


def extract_user_features(user_queries: list[QueryRecord]) -> dict:
    inputs  = [q.input  for q in user_queries]
    outputs = [q.output for q in user_queries]
    n = len(user_queries)
    return {
        "query_count":        n,
        "unique_input_ratio": round(len(set(inputs))  / max(n, 1), 4),
        "avg_input_length":   round(sum(len(s) for s in inputs) / max(n, 1), 2),
        "input_entropy":      round(sum(_shannon_entropy(s) for s in inputs) / max(n, 1), 4),
        "output_diversity":   round(len(set(outputs)) / max(n, 1), 4),
    }


def compute_risk_score(anomaly_score: float) -> float:
    """Map Isolation Forest decision_function output to 0–100 risk (higher = riskier)."""
    clamped = max(-0.5, min(0.5, anomaly_score))
    return round((0.5 - clamped) / 1.0 * 100, 1)


def risk_level(score: float) -> str:
    if   score >= 80: return "CRITICAL"
    elif score >= 60: return "HIGH"
    elif score >= 40: return "MEDIUM"
    return "LOW"


_LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------
def store_audit_log(record: dict) -> str:
    mc = get_minio()
    key = f"{record['partner_id']}/{record['timestamp'][:10]}/{record['batch_id']}.json"
    data = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(BUCKET_AUDITLOG, key, io.BytesIO(data), length=len(data),
                  content_type="application/json")
    return key


def store_theft_report(record: dict) -> None:
    mc = get_minio()
    key = f"{record['partner_id']}/{record['batch_id']}_report.json"
    data = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(BUCKET_REPORTS, key, io.BytesIO(data), length=len(data),
                  content_type="application/json")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    for attempt in range(10):
        try:
            ensure_buckets()
            logger.info("MinIO buckets ready.")
            break
        except Exception as exc:
            logger.warning("MinIO not ready (attempt %d/10): %s", attempt + 1, exc)
            time.sleep(3)
    else:
        logger.error("Could not connect to MinIO after 10 attempts.")
    get_detector()


# ---------------------------------------------------------------------------
# Role-scoped OpenAPI specs
# analyst  : read-only audit + reports
# partner  : analyst paths + POST /batch/analyze + GET /batch/{batch_id}
# admin    : full spec
# ---------------------------------------------------------------------------
_ANALYST_PATHS = {
    "/audit/{partner_id}",
    "/reports/{partner_id}",
    "/reports/{partner_id}/{report_key}",
}
_PARTNER_PATHS = _ANALYST_PATHS | {"/batch/analyze", "/batch/{batch_id}"}


def _filtered_spec(allowed_paths: Optional[set] = None) -> dict:
    spec = app.openapi()
    if allowed_paths is None:
        return spec
    return {**spec, "paths": {p: ops for p, ops in spec.get("paths", {}).items() if p in allowed_paths}}


@app.get("/openapi-analyst.json", include_in_schema=False)
async def openapi_analyst():
    return _filtered_spec(_ANALYST_PATHS)


@app.get("/openapi-partner.json", include_in_schema=False)
async def openapi_partner():
    return _filtered_spec(_PARTNER_PATHS)


@app.get("/openapi-admin.json", include_in_schema=False)
async def openapi_admin_spec():
    return _filtered_spec()


@app.get("/openapi-public.json", include_in_schema=False)
async def openapi_public():
    return _filtered_spec({"/health"})


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
@limiter.limit("10/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    """Issue a JWT for a valid username/password pair."""
    user = _HASHED_USERS.get(form.username)
    if not user or not _bcrypt.checkpw(form.password.encode(), user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = _create_token(form.username, user["role"])
    return TokenResponse(access_token=token, role=user["role"], username=form.username)


@app.get("/auth/me", tags=["auth"])
async def whoami(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's identity and role."""
    return user


# ---------------------------------------------------------------------------
# Operations endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Public liveness probe — returns minimal status only."""
    return {"status": "ok"}


@app.get("/health/detail", response_model=HealthResponse)
async def health_detail(_user: dict = Depends(_ANY_AUTHED)):
    """Full subsystem health check including MinIO, detector, and frontend — requires auth."""
    minio_ok = "ok"
    try:
        get_minio().list_buckets()
    except Exception as exc:
        minio_ok = f"error: {exc}"

    frontend_ok = "ok"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://frontend:80/", timeout=3)
            if r.status_code >= 400:
                frontend_ok = f"error: HTTP {r.status_code}"
    except Exception as exc:
        frontend_ok = f"error: {exc}"

    return HealthResponse(
        status="ok",
        minio=minio_ok,
        detector="loaded" if _detector is not None else "not loaded",
        frontend=frontend_ok,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/stats", response_model=StatsResponse)
async def stats(_user: dict = Depends(_ANY_AUTHED)):
    """Aggregated system statistics for the OE Dashboard."""
    minio_ok = "ok"
    total_partners = 0
    total_batches  = 0
    try:
        mc = get_minio()
        mc.list_buckets()
        partner_ids: set[str] = set()
        for obj in mc.list_objects(BUCKET_AUDITLOG, recursive=True):
            parts = obj.object_name.split("/")
            if parts[0]:
                partner_ids.add(parts[0])
                total_batches += 1
        total_partners = len(partner_ids)
    except Exception as exc:
        minio_ok = f"error: {exc}"

    return StatsResponse(
        total_partners=total_partners,
        total_batches_analyzed=total_batches,
        detector="loaded" if _detector is not None else "not loaded",
        minio=minio_ok,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/stats/partners", response_model=list[PartnerActivityItem])
async def partner_activity(_user: dict = Depends(_ANY_AUTHED)):
    """Per-partner last-seen timestamp and batch count for integration health monitoring."""
    mc = get_minio()
    now = datetime.now(timezone.utc)
    partner_data: dict[str, dict] = {}
    try:
        for obj in mc.list_objects(BUCKET_AUDITLOG, recursive=True):
            parts = obj.object_name.split("/")
            if not parts[0]:
                continue
            pid = parts[0]
            if pid not in partner_data:
                partner_data[pid] = {"total_batches": 0, "last_modified": None}
            partner_data[pid]["total_batches"] += 1
            lm = obj.last_modified
            if lm and lm.tzinfo is None:
                lm = lm.replace(tzinfo=timezone.utc)
            if lm and (
                partner_data[pid]["last_modified"] is None
                or lm > partner_data[pid]["last_modified"]
            ):
                partner_data[pid]["last_modified"] = lm
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    result = []
    for pid, data in sorted(partner_data.items()):
        last_mod = data["last_modified"]
        hours = round((now - last_mod).total_seconds() / 3600, 1) if last_mod else -1.0
        result.append(PartnerActivityItem(
            partner_id=pid,
            total_batches=data["total_batches"],
            last_seen=last_mod.isoformat() if last_mod else "unknown",
            hours_since_last_batch=hours,
        ))
    return result


# ---------------------------------------------------------------------------
# Batch detection endpoint
# ---------------------------------------------------------------------------
@app.post("/batch/analyze", response_model=BatchAnalyzeResponse, tags=["detection"])
async def batch_analyze(
    req: BatchAnalyzeRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(_PARTNER),
):
    """
    Analyze a batch of query records for model theft patterns.
    Per-user behavioral features are extracted and scored by the Isolation Forest.
    Returns per-user risk scores and a batch-level risk assessment.
    """
    batch_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    # Group queries by user
    by_user: dict[str, list[QueryRecord]] = defaultdict(list)
    for q in req.queries:
        by_user[q.query_user].append(q)

    detector = get_detector()
    user_results: list[UserRiskResult] = []

    for query_user, user_queries in by_user.items():
        features = extract_user_features(user_queries)
        feat_vec = np.array([[
            features["query_count"],
            features["unique_input_ratio"],
            features["avg_input_length"],
            features["input_entropy"],
            features["output_diversity"],
        ]])
        pred      = detector.predict(feat_vec)[0]           # 1 = normal, -1 = anomaly
        score_raw = float(detector.decision_function(feat_vec)[0])
        is_anomaly = bool(pred == -1)
        risk  = compute_risk_score(score_raw)
        level = risk_level(risk)
        user_results.append(UserRiskResult(
            query_user=query_user,
            query_count=features["query_count"],
            risk_score=risk,
            risk_level=level,
            anomaly=is_anomaly,
            features=features,
        ))

    batch_risk = (
        max(user_results, key=lambda u: _LEVEL_ORDER[u.risk_level]).risk_level
        if user_results else "LOW"
    )
    flagged = sum(1 for u in user_results if u.risk_level in ("HIGH", "CRITICAL"))

    audit_record = {
        "batch_id":         batch_id,
        "partner_id":       req.partner_id,
        "window_start":     req.window_start,
        "window_end":       req.window_end,
        "total_queries":    len(req.queries),
        "total_users":      len(by_user),
        "flagged_users":    flagged,
        "batch_risk_level": batch_risk,
        "user_results":     [u.model_dump() for u in user_results],
        "timestamp":        ts,
    }

    try:
        log_key = store_audit_log(audit_record)
    except Exception as exc:
        logger.error("Failed to store audit log: %s", exc)
        log_key = "minio-unavailable"

    if batch_risk in ("HIGH", "CRITICAL"):
        background_tasks.add_task(store_theft_report, audit_record)

    return BatchAnalyzeResponse(
        batch_id=batch_id,
        partner_id=req.partner_id,
        window_start=req.window_start,
        window_end=req.window_end,
        total_queries=len(req.queries),
        total_users=len(by_user),
        flagged_users=flagged,
        batch_risk_level=batch_risk,
        user_results=user_results,
        timestamp=ts,
        audit_log_key=log_key,
    )


@app.get("/batch/{batch_id}", tags=["detection"])
async def get_batch_result(batch_id: str, _user: dict = Depends(_PARTNER)):
    """Retrieve the stored result for a previously analyzed batch."""
    mc = get_minio()
    try:
        for obj in mc.list_objects(BUCKET_AUDITLOG, recursive=True):
            if obj.object_name.endswith(f"/{batch_id}.json"):
                response = mc.get_object(BUCKET_AUDITLOG, obj.object_name)
                return json.loads(response.read().decode())
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")


# ---------------------------------------------------------------------------
# Audit + report endpoints
# ---------------------------------------------------------------------------
@app.get("/audit/{partner_id}", tags=["audit"])
async def list_audit_logs(
    partner_id: str,
    date: Optional[str] = None,
    _user: dict = Depends(_ANY_AUTHED),
):
    """List batch audit log entries for a partner (optional date filter YYYY-MM-DD)."""
    mc = get_minio()
    prefix = f"{partner_id}/{date}/" if date else f"{partner_id}/"
    logs = []
    try:
        for obj in mc.list_objects(BUCKET_AUDITLOG, prefix=prefix, recursive=True):
            logs.append({
                "key":           obj.object_name,
                "size":          obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"partner_id": partner_id, "audit_logs": logs}


@app.get("/reports/{partner_id}", tags=["reports"])
async def list_theft_reports(partner_id: str, _user: dict = Depends(_ANY_AUTHED)):
    """List stored theft reports (HIGH/CRITICAL batches) for a partner."""
    mc = get_minio()
    prefix = f"{partner_id}/"
    reports = []
    try:
        for obj in mc.list_objects(BUCKET_REPORTS, prefix=prefix, recursive=True):
            reports.append({
                "key":           obj.object_name,
                "size":          obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"partner_id": partner_id, "theft_reports": reports}


@app.get("/reports/{partner_id}/{report_key:path}", tags=["reports"])
async def get_theft_report(partner_id: str, report_key: str, _user: dict = Depends(_ANY_AUTHED)):
    """Fetch the full content of a specific theft report from MinIO."""
    mc = get_minio()
    key = f"{partner_id}/{report_key}"
    try:
        response = mc.get_object(BUCKET_REPORTS, key)
        return json.loads(response.read().decode())
    except S3Error:
        raise HTTPException(status_code=404, detail="Report not found.")
