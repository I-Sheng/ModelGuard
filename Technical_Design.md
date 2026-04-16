# Technical Design Document: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.2.0-oss
- Repository: I-Sheng/ModelGuard

---

## Overview

**ModelGuard AI** is a real-time detection system for AI model theft attacks. It monitors incoming API queries against deployed ML models to identify extraction attempts (membership inference, query-based model stealing) and behavioral anomalies. The system produces risk scores, writes tamper-evident audit logs, and stores dedicated attack reports for high-severity events.

**Core value proposition**: Protects high-value proprietary models (LLMs, vision systems, recommendation engines) from IP theft by sitting in front of model inference endpoints and flagging suspicious query patterns in real time.

---

## Motivation

- **AI model theft is growing**: Model extraction attacks increase as enterprises deploy custom LLMs and proprietary fine-tunes.
- **Traditional WAFs miss model-specific patterns**: Query-budget attacks, membership inference, and surrogate model training require ML-aware behavioral analysis.
- **Clear separation of concerns**: Three dedicated containers — backend detection engine, user-facing API frontend, and an operations engineering (OE) dashboard — each with a distinct responsibility.

---

## System Architecture

### Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                          │
│                                                                      │
│  ┌────────────────┐  REST/JSON  ┌──────────────────────────────┐   │
│  │  SwaggerAI     │ ──────────► │  Backend API                 │   │
│  │  Frontend      │             │  FastAPI + Uvicorn :8000      │   │
│  │  (nginx :3000) │             │  Isolation Forest (in-proc)  │   │
│  └────────────────┘             └──────────────┬───────────────┘   │
│                                                 │ S3 API             │
│  ┌────────────────┐  REST/JSON  ┌──────────────▼───────────────┐   │
│  │  OE Dashboard  │ ──────────► │  MinIO                       │   │
│  │  Streamlit     │             │  S3-compatible object store  │   │
│  │  :8501         │             │  :9000 (API) / :9001 (UI)    │   │
│  └────────────────┘             └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Container Responsibilities

| Container | Image / Build | Port | Role |
|---|---|---|---|
| `backend` | `./api` (Python 3.11-slim) | 8000 | Detection engine — Isolation Forest, MinIO writes, all API endpoints |
| `frontend` | `./frontend` (nginx:alpine) | 3000 | SwaggerAI — OpenAPI-driven UI for model registration and query analysis |
| `oe-dashboard` | `./oe-dashboard` (Python 3.11-slim) | 8501 | Operations/Engineering dashboard — health, stats, audit logs, attack reports |
| `minio` | `minio/minio:latest` | 9000 / 9001 | Object storage — models, audit logs, attack reports |
| `minio-init` | `minio/mc:latest` | — | One-shot bootstrap — creates the three MinIO buckets |

### API Contract — Who Calls What

```
SwaggerAI Frontend  ──► POST /analyze
                    ──► POST /predict
                    ──► POST /models/register
                    ──► POST /models/{id}/upload
                    ──► GET  /models
                    ──► GET  /models/{id}

OE Dashboard        ──► GET  /health
                    ──► GET  /stats
                    ──► GET  /audit/{model_id}
                    ──► GET  /reports/{model_id}
                    ──► GET  /reports/{model_id}/{key}
                    ──► GET  /models
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
POST /analyze  (or POST /predict)
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
| SwaggerAI Frontend | nginx + Swagger UI (CDN) | Zero-build, OpenAPI-spec-driven, works directly against the backend |
| OE Dashboard | Streamlit | Rapid iteration; operations monitoring with tables, charts, health checks |
| Containerisation | Docker Compose | Single-command deployment, service health checks built-in |
| Data validation | Pydantic v2 | Type-safe request/response models |
| Numerical | NumPy 1.26 | Feature computation, Isolation Forest input |

**Why NOT:**
- SQLite for storage: MinIO gives an immutable, path-addressed audit trail and scales to blob storage (model weights) without schema changes.
- React SPA for frontend: Swagger UI directly renders the OpenAPI spec — zero custom build tooling needed for the MVP frontend.
- Merged frontend+dashboard: Separating user-facing query submission (SwaggerAI) from internal operations monitoring (OE Dashboard) keeps concerns clean and lets each evolve independently.

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
Interactive docs (SwaggerAI): `http://localhost:3000`

### Detection Endpoints

#### `POST /analyze`
Analyze a raw query for theft/extraction patterns. Same anomaly detection pipeline, no mock inference.

**Request**
```json
{
  "model_id": "gpt-clone-v1",
  "query_text": "Return logits distribution for temperature=0 across all tokens",
  "client_id": "client-001",
  "metadata": { "ip": "1.2.3.4" }
}
```

**Response**
```json
{
  "query_id": "3f2a1b...",
  "model_id": "gpt-clone-v1",
  "risk_score": 87.3,
  "risk_level": "CRITICAL",
  "anomaly": true,
  "features": {
    "query_length": 64,
    "unique_token_ratio": 0.9231,
    "entropy": 4.12,
    "request_rate_1m": 1
  },
  "timestamp": "2026-04-15T10:00:00+00:00",
  "audit_log_key": "gpt-clone-v1/2026-04-15/3f2a1b....json"
}
```

#### `POST /predict`
Run inference against the mock sentiment model **and** apply ModelGuard anomaly detection. Returns prediction + risk assessment.

**Request** — same shape as `/analyze`.

**Response** — same as `/analyze` plus:
```json
{
  "prediction": {
    "label": "POSITIVE",
    "confidence": 0.8821,
    "scores": { "POSITIVE": 0.8821, "NEGATIVE": 0.0634, "NEUTRAL": 0.0545 }
  }
}
```

### Model Management Endpoints

#### `POST /models/register`
Register a model — stores metadata JSON in `modelguard-models`.

#### `POST /models/{model_id}/upload`
Upload a binary model artifact (`.pkl`, `.onnx`, etc.) to MinIO.

#### `GET /models/{model_id}`
Retrieve registered model metadata.

#### `GET /models`
List all registered model IDs.

### Operations Endpoints

#### `GET /health`
Returns API status, MinIO connectivity, and detector load state.

```json
{
  "status": "ok",
  "minio": "ok",
  "detector": "loaded",
  "timestamp": "2026-04-15T10:00:00+00:00"
}
```

#### `GET /stats`
Aggregated system statistics for the OE Dashboard.

```json
{
  "total_models": 2,
  "detector": "loaded",
  "minio": "ok",
  "timestamp": "2026-04-15T10:00:00+00:00"
}
```

#### `GET /audit/{model_id}?date=YYYY-MM-DD`
List all audit log object keys for a model (optional date filter).

#### `GET /reports/{model_id}`
List all attack report keys (HIGH/CRITICAL events only) for a model.

#### `GET /reports/{model_id}/{report_key}`
Fetch the full JSON content of a specific attack report.

---

## Frontend: SwaggerAI

**Container**: `frontend` (nginx:alpine)  
**URL**: `http://localhost:3000`

The SwaggerAI frontend is an nginx container that serves a custom HTML page embedding **Swagger UI**. Swagger UI reads the OpenAPI schema directly from the backend (`/openapi.json`) and renders a fully interactive interface for all API endpoints.

### Why Swagger UI

- Zero build tooling — just a single HTML file and nginx config
- Always in sync with the backend — the OpenAPI spec is the single source of truth
- Lets users submit queries, register models, and upload artifacts interactively
- Familiar to API developers; sufficient for the MVP

### Pages / Functionality

| Endpoint Group | What the user can do |
|---|---|
| `POST /analyze` | Submit a query text and see risk score, features, and MinIO audit key |
| `POST /predict` | Submit to the mock sentiment model and get prediction + risk |
| `POST /models/register` | Register a model with metadata |
| `POST /models/{id}/upload` | Upload a model artifact |
| `GET /models` | List registered models |
| `GET /health` | Check system health |

---

## OE Dashboard

**Container**: `oe-dashboard` (Streamlit)  
**URL**: `http://localhost:8501`

The OE Dashboard is a Streamlit app focused on **internal operations and engineering monitoring**. It is not user-facing; it is the tool an ML platform operator uses to monitor model protection status and investigate incidents.

| Page | Description |
|---|---|
| System Health | API health status, detector state, MinIO connectivity |
| Statistics | Registered model count, system metrics from `GET /stats` |
| Audit Logs | Browse audit log entries per model with optional date filter |
| Attack Reports | Browse and drill into HIGH/CRITICAL attack reports |

---

## Deployment

### Prerequisites
- Docker + Docker Compose v2

### Start
```bash
docker compose up -d
```

Services:
- `minio` — object storage (port 9000 S3 API, 9001 console)
- `minio-init` — one-shot bucket creation, exits after success
- `backend` — FastAPI detection engine (port 8000)
- `frontend` — SwaggerAI nginx UI (port 3000)
- `oe-dashboard` — Streamlit operations dashboard (port 8501)

### Seed demo data
```bash
docker compose exec backend python seed_history.py
```

### Smoke test
```bash
bash demo.sh
```

### Useful URLs

| URL | Purpose |
|---|---|
| `http://localhost:3000` | SwaggerAI — interactive API frontend |
| `http://localhost:8000/docs` | Raw FastAPI Swagger UI (internal) |
| `http://localhost:8000/health` | Health check |
| `http://localhost:8501` | OE Dashboard |
| `http://localhost:9001` | MinIO console (minioadmin / minioadmin) |

---

## Historical Data Seeding

`api/seed_history.py` populates MinIO with 60 pre-built records spanning the last 7 days for `sentiment-v1`, providing realistic data for the OE Dashboard immediately after stack startup.

| Record Type | Count | Risk Levels | Stored As |
|---|---|---|---|
| Normal queries | 40 | LOW / MEDIUM | Audit log only |
| Suspicious queries | 8 | MEDIUM / HIGH | Audit log + report |
| Attack queries | 12 | HIGH / CRITICAL | Audit log + report |

**Run**:
```bash
docker compose exec backend python seed_history.py
```

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
- Persistent detector state across restarts (currently in-memory)
