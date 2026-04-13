# Technical Design Document: ModelGuard AI

---

- Status: MVP — Baseline Release
- Version: 0.1.0-oss
- Repository: I-Sheng/ModelGuard

---

## Overview

**ModelGuard AI** is a real-time detection system for AI model theft attacks. It monitors incoming API queries against deployed ML models to identify extraction attempts (membership inference, query-based model stealing) and behavioral anomalies. The system produces risk scores, writes tamper-evident audit logs, and stores dedicated attack reports for high-severity events.

**Core value proposition**: Protects high-value proprietary models (LLMs, vision systems, recommendation engines) from IP theft by sitting in front of model inference endpoints and flagging suspicious query patterns in real time.

---

## Motivation

- **AI model theft is growing**: Model extraction attacks increase as enterprises deploy custom LLMs and proprietary fine-tunes.
- **Traditional WAFs miss model-specific patterns**: Query-budget attacks, membership inference, and surrogate model training require ML-aware behavioral analysis.
- **Low operational overhead**: The MVP runs as a single Docker Compose stack with no external dependencies beyond MinIO.

---

## System Architecture

### Component Map

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                  │
│                                                         │
│  ┌──────────────┐    HTTP     ┌─────────────────────┐   │
│  │  Streamlit   │ ──────────► │   FastAPI + Uvicorn │   │
│  │  Dashboard   │             │   (port 8000)       │   │
│  │  (port 8501) │             └────────┬────────────┘   │
│  └──────────────┘                      │ S3 API          │
│                                        ▼                 │
│                              ┌─────────────────────┐    │
│                              │        MinIO        │    │
│                              │  S3-compatible      │    │
│                              │  object storage     │    │
│                              │  (port 9000/9001)   │    │
│                              └─────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### MinIO Bucket Layout

| Bucket | Purpose | Key Pattern |
|---|---|---|
| `modelguard-models` | Model metadata + binary artifacts | `{model_id}/metadata.json`, `{model_id}/artifacts/{filename}` |
| `modelguard-auditlog` | Every query audit record | `{model_id}/{YYYY-MM-DD}/{query_id}.json` |
| `modelguard-reports` | HIGH/CRITICAL attack reports only | `{model_id}/{query_id}_report.json` |

### Data Flow

```
Client Request
     │
     ▼
POST /predict  (or POST /analyze)
     │
     ├─ 1. Feature Extraction
     │       query_length, unique_token_ratio,
     │       shannon_entropy, request_rate_1m
     │
     ├─ 2. Isolation Forest inference
     │       → anomaly flag (bool)
     │       → decision_function score → risk score 0–100
     │       → risk level LOW / MEDIUM / HIGH / CRITICAL
     │
     ├─ 3. Store audit record in MinIO (always)
     │       bucket: modelguard-auditlog
     │
     ├─ 4. Store attack report in MinIO (HIGH/CRITICAL only)
     │       bucket: modelguard-reports  [background task]
     │
     └─ 5. Return JSON response to caller
```

---

## Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| API framework | FastAPI + Uvicorn | Async I/O, auto OpenAPI docs at `/docs`, Pydantic validation |
| Anomaly detection | scikit-learn `IsolationForest` | Unsupervised, no labelled attack data required |
| Object storage | MinIO (S3-compatible) | Self-hosted, no cloud dependency, tamper-evident audit trail |
| Dashboard | Streamlit | Rapid iteration; sufficient for MVP monitoring UI |
| Containerisation | Docker Compose | Single-command deployment, service health checks built-in |
| Data validation | Pydantic v2 | Type-safe request/response models |
| Numerical | NumPy 1.26 | Feature computation, Isolation Forest input |

**Why NOT:**
- SQLite for storage: MinIO gives an immutable, path-addressed audit trail and scales to blob storage (model weights) without schema changes.
- React frontend: Streamlit delivers the required dashboard pages with far less development overhead at MVP stage.

---

## Anomaly Detection Design

### Feature Vector (4 dimensions)

| Feature | Description | Attack Signal |
|---|---|---|
| `query_length` | Character count of query text | Extraction queries are typically verbose |
| `unique_token_ratio` | `unique_tokens / total_tokens` | Systematic probing uses repetitive patterns |
| `entropy` | Shannon entropy of query characters | Adversarial payloads have distinct entropy profiles |
| `request_rate_1m` | Queries from this process in the last 60 s | Burst queries indicate automated extraction |

### Isolation Forest Configuration

```python
IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
```

Trained at startup on 500 synthetic normal samples drawn from:

```python
normal ~ N(loc=[120, 0.6, 3.5, 2.0], scale=[40, 0.1, 0.5, 0.8])
#              query_len  utr   entropy  rate
```

### Risk Score Mapping

The `decision_function` output (typically `[-0.5, +0.5]`) is mapped to `[0, 100]`:

```
risk_score = (0.5 - decision_function_score) / 1.0 × 100
```

| Risk Score | Level | Meaning |
|---|---|---|
| 0 – 39 | LOW | Normal query pattern |
| 40 – 59 | MEDIUM | Mildly anomalous |
| 60 – 79 | HIGH | Likely extraction attempt; report stored |
| 80 – 100 | CRITICAL | Strong extraction signal; report stored |

---

## API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

### Core Endpoints

#### `POST /predict`
Run inference against the mock sentiment model **and** apply ModelGuard anomaly detection. Every call is audited.

**Request**
```json
{
  "model_id": "sentiment-v1",
  "query_text": "I love this product!",
  "client_id": "user-001",
  "metadata": {}
}
```

**Response**
```json
{
  "query_id": "3f2a1b...",
  "model_id": "sentiment-v1",
  "prediction": {
    "label": "POSITIVE",
    "confidence": 0.8821,
    "scores": {"POSITIVE": 0.8821, "NEGATIVE": 0.0634, "NEUTRAL": 0.0545}
  },
  "risk_score": 12.5,
  "risk_level": "LOW",
  "anomaly": false,
  "features": {
    "query_length": 22,
    "unique_token_ratio": 1.0,
    "entropy": 4.12,
    "request_rate_1m": 1
  },
  "timestamp": "2026-04-12T10:00:00+00:00",
  "audit_log_key": "sentiment-v1/2026-04-12/3f2a1b....json"
}
```

#### `POST /analyze`
Analyze any raw query text against a model without invoking a mock inference function. Same anomaly detection pipeline as `/predict`.

**Request** — same shape as `/predict` minus the `prediction` field in the response.

#### `GET /audit/{model_id}`
List all audit log object keys for a model stored in `modelguard-auditlog`.

Query param: `date=YYYY-MM-DD` (optional filter).

**Response**
```json
{
  "model_id": "sentiment-v1",
  "audit_logs": [
    {"key": "sentiment-v1/2026-04-12/abc.json", "size": 512, "last_modified": "..."}
  ]
}
```

#### `GET /reports/{model_id}`
List all attack report keys for a model stored in `modelguard-reports` (HIGH/CRITICAL events only).

#### `GET /reports/{model_id}/{report_key}`
Fetch the full JSON content of a specific attack report.

#### `POST /models/register`
Register a model — stores metadata JSON in `modelguard-models`.

```json
{
  "model_id": "sentiment-v1",
  "name": "Sentiment Classifier",
  "version": "1.0.0",
  "description": "Mock sentiment model (POSITIVE/NEGATIVE/NEUTRAL)",
  "owner": "ml-team"
}
```

#### `POST /models/{model_id}/upload`
Upload a binary model artifact (`.pkl`, `.onnx`, etc.) to MinIO via multipart form.

#### `GET /models/{model_id}`
Retrieve registered model metadata.

#### `GET /models`
List all registered model IDs.

#### `GET /health`
Returns API status, MinIO connectivity, and detector load state.

---

## Mock Model: `sentiment-v1`

A deterministic, rule-based sentiment classifier used for development and demo purposes. It requires no trained weights and produces stable, reproducible outputs for the same input.

**Classes**: `POSITIVE`, `NEGATIVE`, `NEUTRAL`

**Logic**: Scores are derived from positive/negative keyword hit counts, seeded with a hash of the input text for deterministic noise. The output is a label, a confidence score, and a full score dict.

**Registration**:
```bash
curl -X POST http://localhost:8000/models/register \
  -H "Content-Type: application/json" \
  -d '{"model_id":"sentiment-v1","name":"Sentiment Classifier","version":"1.0.0","owner":"ml-team"}'
```

---

## Historical Data Seeding

`api/seed_history.py` populates MinIO with 60 pre-built records spanning the last 7 days for `sentiment-v1`, providing realistic data for `GET /audit` and `GET /reports` immediately after stack startup.

| Record Type | Count | Risk Levels | Stored As |
|---|---|---|---|
| Normal queries | 40 | LOW / MEDIUM | Audit log only |
| Suspicious queries | 8 | MEDIUM / HIGH | Audit log + report |
| Attack queries | 12 | HIGH / CRITICAL | Audit log + report |

**Run**:
```bash
docker compose exec api python seed_history.py
```

---

## Dashboard (Streamlit)

URL: `http://localhost:8501`

| Page | Description |
|---|---|
| Dashboard | Model count, detection engine status, risk level reference chart |
| Analyze Query | Submit a query to `/analyze`, view risk score and feature vector |
| Register Model | Form to register a new model via `/models/register` |
| Audit Logs | Browse audit log entries per model with optional date filter |
| Attack Reports | Browse and drill into HIGH/CRITICAL attack reports |

---

## Deployment

### Prerequisites
- Docker + Docker Compose

### Start
```bash
docker compose up -d
```

Services:
- `minio` — object storage (port 9000 S3 API, 9001 console)
- `minio-init` — one-shot bucket creation, exits after success
- `api` — FastAPI backend (port 8000)
- `dashboard` — Streamlit frontend (port 8501)

### Seed demo data
```bash
docker compose exec api python seed_history.py
```

### Smoke test
```bash
bash demo.sh
```

### Useful URLs

| URL | Purpose |
|---|---|
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |
| `http://localhost:8000/health` | Health check |
| `http://localhost:8501` | Streamlit dashboard |
| `http://localhost:9001` | MinIO console (minioadmin / minioadmin) |

---

## Out of Scope (MVP)

- Agentic auto-mitigation (block/quarantine attackers)
- Multi-tenant support
- Enterprise auth (API keys, JWT, SAML/OIDC)
- Rate limiting middleware
- Transformer-based detectors
- Kubernetes / Helm deployment
- Compliance (SOC 2, GDPR)
- WebSocket live-push to dashboard
- Email / Slack alerting
