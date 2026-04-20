"""
ModelGuard AI - API Query Monitor
Detects model theft attacks via behavioral anomaly detection.
MinIO is used for: model artifact storage, audit log archival, attack report storage.
"""

import os
import io
import json
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from minio import Minio
from minio.error import S3Error
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("modelguard")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ModelGuard AI",
    description="Real-time ML model theft detection API",
    version="0.1.0-oss",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth — JWT + role-based access control
# ---------------------------------------------------------------------------
JWT_SECRET    = os.getenv("JWT_SECRET_KEY", "modelguard-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2  = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Demo users: username → {password, role}
# Roles: "ml_user" (predict + models), "customer" (+ audit + reports), "admin" (all)
_USERS: dict[str, dict] = {
    "ml_user":   {"password": "ml_password",       "role": "ml_user"},
    "customer1": {"password": "customer_password",  "role": "customer"},
    "admin":     {"password": "admin_password",     "role": "admin"},
}
# Pre-hash at startup (done once, not per-request)
_HASHED_USERS = {
    u: {"hashed_password": _pwd_ctx.hash(v["password"]), "role": v["role"]}
    for u, v in _USERS.items()
}


def _create_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "role": role, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(token: str = Depends(_oauth2)) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str     = payload.get("role")
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


_ANY_AUTHED  = require_role("ml_user", "customer", "admin")
_CUSTOMER    = require_role("customer", "admin")


# ---------------------------------------------------------------------------
# MinIO client
# ---------------------------------------------------------------------------
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

BUCKET_MODELS   = "modelguard-models"
BUCKET_AUDITLOG = "modelguard-auditlog"
BUCKET_REPORTS  = "modelguard-reports"

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
    for bucket in [BUCKET_MODELS, BUCKET_AUDITLOG, BUCKET_REPORTS]:
        if not mc.bucket_exists(bucket):
            mc.make_bucket(bucket)
            logger.info("Created bucket: %s", bucket)


# ---------------------------------------------------------------------------
# In-memory anomaly detector (Isolation Forest)
# Feature vector: [query_length, unique_token_ratio, entropy, request_rate_1m]
# ---------------------------------------------------------------------------
_detector: Optional[IsolationForest] = None
_query_window: list[float] = []   # timestamps for rate estimation

NORMAL_SEED = np.random.default_rng(42)
_TRAIN_DATA = NORMAL_SEED.normal(
    loc=[120, 0.6, 3.5, 2.0],
    scale=[40, 0.1, 0.5, 0.8],
    size=(500, 4),
)


def get_detector() -> IsolationForest:
    global _detector
    if _detector is None:
        _detector = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
        _detector.fit(_TRAIN_DATA)
        logger.info("Isolation Forest trained on %d synthetic samples.", len(_TRAIN_DATA))
    return _detector


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    model_id: str = Field(..., description="Target model identifier")
    query_text: str = Field(..., description="Raw query/prompt sent to the model")
    client_id: Optional[str] = Field(None, description="Caller identifier for rate tracking")
    metadata: Optional[dict] = Field(None, description="Extra metadata (IP, user-agent, etc.)")


class RiskResponse(BaseModel):
    query_id: str
    model_id: str
    risk_score: float          # 0–100
    risk_level: str            # LOW / MEDIUM / HIGH / CRITICAL
    anomaly: bool
    features: dict
    timestamp: str
    audit_log_key: str         # MinIO object key where audit record was stored


class HealthResponse(BaseModel):
    status: str
    minio: str
    detector: str
    timestamp: str


class StatsResponse(BaseModel):
    total_models: int
    detector: str
    minio: str
    timestamp: str


class ModelRegistration(BaseModel):
    model_id: str
    name: str
    version: str
    description: Optional[str] = None
    owner: Optional[str] = None


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------
def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    freq = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * np.log2(c / n) for c in freq.values())


def extract_features(query: str, client_id: Optional[str]) -> dict:
    tokens = query.split()
    unique_ratio = len(set(tokens)) / max(len(tokens), 1)
    entropy = _shannon_entropy(query)

    now = time.time()
    _query_window.append(now)
    # keep only last 60 seconds
    _query_window[:] = [t for t in _query_window if now - t <= 60]
    request_rate = len(_query_window)

    return {
        "query_length": len(query),
        "unique_token_ratio": round(unique_ratio, 4),
        "entropy": round(entropy, 4),
        "request_rate_1m": request_rate,
    }


def compute_risk_score(anomaly_score: float) -> float:
    """Map Isolation Forest decision_function score to 0–100 risk (higher = riskier)."""
    # decision_function returns negative for anomalies; typical range ~ [-0.5, 0.5]
    clamped = max(-0.5, min(0.5, anomaly_score))
    risk = (0.5 - clamped) / 1.0 * 100
    return round(risk, 1)


def risk_level(score: float) -> str:
    if score >= 80:
        return "CRITICAL"
    elif score >= 60:
        return "HIGH"
    elif score >= 40:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------
def store_audit_log(record: dict) -> str:
    mc = get_minio()
    key = f"{record['model_id']}/{record['timestamp'][:10]}/{record['query_id']}.json"
    data = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(
        BUCKET_AUDITLOG,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/json",
    )
    return key


def store_attack_report(record: dict) -> str:
    mc = get_minio()
    key = f"{record['model_id']}/{record['query_id']}_report.json"
    data = json.dumps(record, ensure_ascii=False).encode()
    mc.put_object(
        BUCKET_REPORTS,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/json",
    )
    return key


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    # MinIO bucket creation with retry (service may still be starting)
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
# Role-scoped OpenAPI specs (served to the frontend after login)
# ml_user  : GET /models, POST /predict
# customer : ml_user paths + GET /audit/{model_id} + GET /reports/*
# admin    : full spec (all paths, including those not exposed to other roles)
# ---------------------------------------------------------------------------
_ML_USER_PATHS  = {"/models", "/predict"}
_CUSTOMER_PATHS = _ML_USER_PATHS | {
    "/audit/{model_id}",
    "/reports/{model_id}",
    "/reports/{model_id}/{report_key}",
}


def _filtered_spec(allowed_paths: Optional[set] = None) -> dict:
    spec = app.openapi()
    if allowed_paths is None:
        return spec
    return {**spec, "paths": {p: ops for p, ops in spec.get("paths", {}).items() if p in allowed_paths}}


@app.get("/openapi-ml.json", include_in_schema=False)
async def openapi_ml():
    return _filtered_spec(_ML_USER_PATHS)


@app.get("/openapi-customer.json", include_in_schema=False)
async def openapi_customer():
    return _filtered_spec(_CUSTOMER_PATHS)


@app.get("/openapi-admin.json", include_in_schema=False)
async def openapi_admin_spec():
    return _filtered_spec()


@app.get("/openapi-public.json", include_in_schema=False)
async def openapi_public():
    return _filtered_spec({"/health"})


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """Issue a JWT for a valid username/password pair."""
    user = _HASHED_USERS.get(form.username)
    if not user or not _pwd_ctx.verify(form.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = _create_token(form.username, user["role"])
    return TokenResponse(access_token=token, role=user["role"], username=form.username)


@app.get("/auth/me", tags=["auth"])
async def whoami(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's identity and role."""
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    minio_ok = "ok"
    try:
        get_minio().list_buckets()
    except Exception as exc:
        minio_ok = f"error: {exc}"

    return HealthResponse(
        status="ok",
        minio=minio_ok,
        detector="loaded" if _detector is not None else "not loaded",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/stats", response_model=StatsResponse)
async def stats():
    """Aggregated system statistics for the OE Dashboard."""
    minio_ok = "ok"
    total_models = 0
    try:
        mc = get_minio()
        mc.list_buckets()
        objects = mc.list_objects(BUCKET_MODELS, recursive=False)
        for _ in objects:
            total_models += 1
    except Exception as exc:
        minio_ok = f"error: {exc}"

    return StatsResponse(
        total_models=total_models,
        detector="loaded" if _detector is not None else "not loaded",
        minio=minio_ok,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/analyze", response_model=RiskResponse)
async def analyze_query(req: QueryRequest, background_tasks: BackgroundTasks,
                        _user: dict = Depends(_ANY_AUTHED)):
    """
    Analyze an incoming ML API query for theft/extraction patterns.
    Stores audit log in MinIO; stores attack report for HIGH/CRITICAL events.
    """
    query_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    features = extract_features(req.query_text, req.client_id)
    feat_vec = np.array([[
        features["query_length"],
        features["unique_token_ratio"],
        features["entropy"],
        features["request_rate_1m"],
    ]])

    detector = get_detector()
    pred = detector.predict(feat_vec)[0]          # 1 = normal, -1 = anomaly
    score_raw = float(detector.decision_function(feat_vec)[0])
    is_anomaly = bool(pred == -1)
    risk = compute_risk_score(score_raw)
    level = risk_level(risk)

    audit_record = {
        "query_id": query_id,
        "model_id": req.model_id,
        "client_id": req.client_id,
        "query_text": req.query_text[:500],  # truncate PII
        "features": features,
        "risk_score": risk,
        "risk_level": level,
        "anomaly": is_anomaly,
        "timestamp": ts,
        "metadata": req.metadata or {},
    }

    # Store audit log in MinIO (always)
    try:
        log_key = store_audit_log(audit_record)
    except Exception as exc:
        logger.error("Failed to store audit log: %s", exc)
        log_key = "minio-unavailable"

    # For HIGH/CRITICAL events, also store a dedicated attack report
    if is_anomaly and level in ("HIGH", "CRITICAL"):
        background_tasks.add_task(store_attack_report, audit_record)

    return RiskResponse(
        query_id=query_id,
        model_id=req.model_id,
        risk_score=risk,
        risk_level=level,
        anomaly=is_anomaly,
        features=features,
        timestamp=ts,
        audit_log_key=log_key,
    )


@app.post("/models/register")
async def register_model(reg: ModelRegistration):
    """Register a model — stores its metadata as a JSON artifact in MinIO."""
    mc = get_minio()
    key = f"{reg.model_id}/metadata.json"
    payload = {
        **reg.model_dump(),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    try:
        mc.put_object(
            BUCKET_MODELS,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type="application/json",
        )
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "registered", "key": key, "bucket": BUCKET_MODELS}


@app.post("/models/{model_id}/upload")
async def upload_model_artifact(model_id: str, file: UploadFile = File(...)):
    """Upload a binary model artifact (e.g., .pkl, .onnx) to MinIO."""
    mc = get_minio()
    content = await file.read()
    key = f"{model_id}/artifacts/{file.filename}"
    try:
        mc.put_object(
            BUCKET_MODELS,
            key,
            io.BytesIO(content),
            length=len(content),
            content_type=file.content_type or "application/octet-stream",
        )
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "uploaded", "key": key, "size_bytes": len(content)}


@app.get("/models/{model_id}")
async def get_model_info(model_id: str):
    """Retrieve registered model metadata from MinIO."""
    mc = get_minio()
    key = f"{model_id}/metadata.json"
    try:
        response = mc.get_object(BUCKET_MODELS, key)
        data = json.loads(response.read().decode())
        return data
    except S3Error:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@app.get("/models")
async def list_models(_user: dict = Depends(_ANY_AUTHED)):
    """List all registered models from MinIO."""
    mc = get_minio()
    models = []
    try:
        objects = mc.list_objects(BUCKET_MODELS, recursive=False)
        for obj in objects:
            model_id = obj.object_name.rstrip("/")
            models.append({"model_id": model_id})
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"models": models}


@app.get("/audit/{model_id}")
async def list_audit_logs(model_id: str, date: Optional[str] = None,
                          _user: dict = Depends(_CUSTOMER)):
    """List audit log entries for a model (optionally filtered by date YYYY-MM-DD)."""
    mc = get_minio()
    prefix = f"{model_id}/{date}/" if date else f"{model_id}/"
    logs = []
    try:
        objects = mc.list_objects(BUCKET_AUDITLOG, prefix=prefix, recursive=True)
        for obj in objects:
            logs.append({
                "key": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"model_id": model_id, "audit_logs": logs}


@app.get("/reports/{model_id}")
async def list_attack_reports(model_id: str, _user: dict = Depends(_CUSTOMER)):
    """List stored attack reports (HIGH/CRITICAL events) for a model."""
    mc = get_minio()
    prefix = f"{model_id}/"
    reports = []
    try:
        objects = mc.list_objects(BUCKET_REPORTS, prefix=prefix, recursive=True)
        for obj in objects:
            reports.append({
                "key": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
    except S3Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"model_id": model_id, "attack_reports": reports}


@app.get("/reports/{model_id}/{report_key:path}")
async def get_attack_report(model_id: str, report_key: str, _user: dict = Depends(_CUSTOMER)):
    """Fetch the full content of a specific attack report from MinIO."""
    mc = get_minio()
    key = f"{model_id}/{report_key}"
    try:
        response = mc.get_object(BUCKET_REPORTS, key)
        return json.loads(response.read().decode())
    except S3Error:
        raise HTTPException(status_code=404, detail="Report not found.")


# ---------------------------------------------------------------------------
# Mock model — sentiment classifier
# POST /predict  →  run inference + anomaly detection in one call
# ---------------------------------------------------------------------------
_POSITIVE_WORDS = {"love", "great", "excellent", "amazing", "good", "best",
                   "fantastic", "wonderful", "happy", "perfect", "awesome"}
_NEGATIVE_WORDS = {"hate", "terrible", "awful", "bad", "worst", "horrible",
                   "poor", "disappointing", "broken", "useless", "annoying"}


def _mock_sentiment(text: str) -> dict:
    """Rule-based mock sentiment classifier. Returns label + confidence scores."""
    words = set(text.lower().split())
    pos_hits = len(words & _POSITIVE_WORDS)
    neg_hits = len(words & _NEGATIVE_WORDS)

    rng = np.random.default_rng(abs(hash(text)) % (2 ** 31))
    base = rng.uniform(0.05, 0.15)

    if pos_hits > neg_hits:
        conf_pos = rng.uniform(0.65, 0.95)
        conf_neg = rng.uniform(0.02, 0.15)
    elif neg_hits > pos_hits:
        conf_neg = rng.uniform(0.65, 0.95)
        conf_pos = rng.uniform(0.02, 0.15)
    else:
        conf_pos = rng.uniform(0.25, 0.45)
        conf_neg = rng.uniform(0.25, 0.45)

    conf_neu = max(0.0, 1.0 - conf_pos - conf_neg)
    scores = {
        "POSITIVE": round(float(conf_pos), 4),
        "NEGATIVE": round(float(conf_neg), 4),
        "NEUTRAL":  round(float(conf_neu), 4),
    }
    label = max(scores, key=scores.__getitem__)
    return {"label": label, "confidence": scores[label], "scores": scores}


class PredictRequest(BaseModel):
    model_id: str = Field(..., description="Target model identifier")
    query_text: str = Field(..., description="Text to classify")
    client_id: Optional[str] = Field(None, description="Caller identifier")
    metadata: Optional[dict] = Field(None, description="Extra metadata")


@app.post("/predict")
async def predict(req: PredictRequest, background_tasks: BackgroundTasks,
                  _user: dict = Depends(_ANY_AUTHED)):
    """
    Run inference against the mock sentiment model AND apply ModelGuard anomaly
    detection.  Returns the model prediction together with a risk assessment and
    the MinIO audit-log key so every call is fully traceable.
    """
    query_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    # --- mock inference ---
    prediction = _mock_sentiment(req.query_text)

    # --- anomaly detection (same pipeline as /analyze) ---
    features = extract_features(req.query_text, req.client_id)
    feat_vec = np.array([[
        features["query_length"],
        features["unique_token_ratio"],
        features["entropy"],
        features["request_rate_1m"],
    ]])
    detector = get_detector()
    pred_label = detector.predict(feat_vec)[0]
    score_raw = float(detector.decision_function(feat_vec)[0])
    is_anomaly = bool(pred_label == -1)
    risk = compute_risk_score(score_raw)
    level = risk_level(risk)

    audit_record = {
        "query_id": query_id,
        "model_id": req.model_id,
        "client_id": req.client_id,
        "query_text": req.query_text[:500],
        "features": features,
        "risk_score": risk,
        "risk_level": level,
        "anomaly": is_anomaly,
        "timestamp": ts,
        "metadata": req.metadata or {},
        "endpoint": "predict",
        "prediction": prediction,
    }

    try:
        log_key = store_audit_log(audit_record)
    except Exception as exc:
        logger.error("Failed to store audit log: %s", exc)
        log_key = "minio-unavailable"

    if is_anomaly and level in ("HIGH", "CRITICAL"):
        background_tasks.add_task(store_attack_report, audit_record)

    return {
        "query_id": query_id,
        "model_id": req.model_id,
        "prediction": prediction,
        "risk_score": risk,
        "risk_level": level,
        "anomaly": is_anomaly,
        "features": features,
        "timestamp": ts,
        "audit_log_key": log_key,
    }
