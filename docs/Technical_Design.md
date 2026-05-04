# Technical Design Document: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.3.0-oss
- Repository: I-Sheng/ModelGuard

---

## Overview

**ModelGuard AI** is a batch-mode model theft detection service for AI companies. Partner companies (e.g., OpenAI, Anthropic, or any API-based AI provider) periodically submit a window of their query logs — typically one hour of production traffic — and ModelGuard analyzes the batch to identify users who may be systematically extracting the partner's model through high-volume, structured querying.

**Core value proposition**: AI companies protect their proprietary models by submitting query logs to ModelGuard. ModelGuard's Isolation Forest detector identifies users whose query behavior matches known model-extraction patterns and returns per-user risk scores along with a batch-level risk assessment. HIGH and CRITICAL batches trigger a stored theft report.

---

## Motivation

- **Model theft is asymmetric**: An attacker only needs to make enough queries to approximate model behavior; the model owner bears the full cost of training and serving. Early detection shrinks the window of exploitation.
- **Batch analysis is practical**: AI companies already collect query logs for compliance and billing. Submitting a periodic log batch requires no changes to the inference path and no in-line latency impact.
- **ML-aware detection**: Traditional WAFs inspect individual requests. ModelGuard computes cross-query behavioral features per user — patterns that only emerge across many requests over time.

---

## System Architecture

### Component Map

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Docker Compose Stack                               │
│                                                                               │
│  ┌──────────────────┐   REST + JWT    ┌──────────────────┐   S3 API          │
│  │  SwaggerAI       │ ──────────────► │  Backend API     │ ──────────────►   │
│  │  Frontend        │                 │  FastAPI :8000   │                   │
│  │  nginx :3000     │                 │                  │  ┌─────────────┐  │
│  │                  │                 │  ● JWT Auth+RBAC │  │  MinIO      │  │
│  │  Role-scoped     │                 │  ● Isolation     │  │  :9000      │  │
│  │  OpenAPI spec    │                 │    Forest        │  │  :9001(UI)  │  │
│  └──────────────────┘                 │  ● MinIO writes  │  └─────────────┘  │
│                                       └──────────────────┘                   │
│  ┌──────────────────┐   REST + JWT           ▲                               │
│  │  OE Dashboard    │ ──────────────────────►│                               │
│  │  Streamlit :8501 │   /health/detail        │                               │
│  │                  │   /stats                │                               │
│  │  Auto-logins as  │   /audit/{partner_id}   │                               │
│  │  admin on start  │   /reports/{partner_id} │                               │
│  └──────────────────┘                        ─┘                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Container Responsibilities

| Container | Image / Build | Port | Role |
|---|---|---|---|
| `backend` | `./api` (Python 3.11-slim) | 8000 | Detection engine — JWT auth + RBAC, Isolation Forest, MinIO writes, all API endpoints |
| `frontend` | `./frontend` (nginx:alpine) | 3000 | SwaggerAI — role-scoped OpenAPI UI; loads filtered spec after JWT login |
| `oe-dashboard` | `./oe-dashboard` (Python 3.11-slim) | 8501 | Operations/Engineering dashboard — authenticates as admin, health, stats, audit logs, theft reports |
| `minio` | `minio/minio:latest` | 9000 / 9001 | Object storage — detection models, audit logs, theft reports |
| `minio-init` | `minio/mc:latest` | — | One-shot bootstrap — creates the three MinIO buckets |

### API Contract — Who Calls What

```
SwaggerAI Frontend  ──► POST /auth/login              (public — obtain JWT)
                    ──► GET  /openapi-{role}.json      (public — role-scoped spec)
                    ──► POST /batch/analyze            (Bearer JWT, partner+)
                    ──► GET  /batch/{batch_id}         (Bearer JWT, partner+)
                    ──► GET  /audit/{partner_id}       (Bearer JWT, partner+)
                    ──► GET  /reports/{partner_id}     (Bearer JWT, partner+)
                    ──► GET  /reports/{partner_id}/{key} (Bearer JWT, partner+)

OE Dashboard        ──► POST /auth/login              (auto-login as admin on startup)
                    ──► GET  /health/detail            (Bearer JWT required)
                    ──► GET  /stats                    (public)
                    ──► GET  /audit/{partner_id}       (Bearer JWT, partner+)
                    ──► GET  /reports/{partner_id}     (Bearer JWT, partner+)
                    ──► GET  /reports/{partner_id}/{key} (Bearer JWT, partner+)
```

### MinIO Bucket Layout

| Bucket | Purpose | Key Pattern |
|---|---|---|
| `modelguard-detectors` | Trained Isolation Forest model files | `{version}/detector.pkl` |
| `modelguard-auditlog` | Every batch analysis audit record | `{partner_id}/{YYYY-MM-DD}/{batch_id}.json` |
| `modelguard-reports` | HIGH/CRITICAL theft reports only | `{partner_id}/{batch_id}_report.json` |

### Data Flow

```
Partner submits batch
     │
     ▼
POST /batch/analyze
     │
     ├─ 1. JWT verification + role check
     │
     ├─ 2. Per-user feature extraction (for each unique query_user in batch)
     │       query_count, unique_input_ratio, avg_input_length,
     │       input_entropy, output_diversity
     │
     ├─ 3. Isolation Forest inference (per user)
     │       → anomaly flag (bool) per user
     │       → decision_function score → risk score 0–100
     │       → user risk level LOW / MEDIUM / HIGH / CRITICAL
     │       → batch risk level = max across all users
     │
     ├─ 4. Store batch audit record in MinIO (always)
     │       bucket: modelguard-auditlog
     │
     ├─ 5. Store theft report in MinIO (HIGH/CRITICAL only)
     │       bucket: modelguard-reports  [background task]
     │
     └─ 6. Return JSON response to caller
```

---

## Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| API framework | FastAPI + Uvicorn | Async I/O, auto OpenAPI docs at `/docs`, Pydantic validation |
| Auth | `python-jose` (JWT) + `bcrypt` | HS256 signed tokens; bcrypt for password hashing at startup |
| Anomaly detection | scikit-learn `IsolationForest` | Unsupervised, no labelled theft data required; model persisted to MinIO |
| Object storage | MinIO (S3-compatible) | Self-hosted, no cloud dependency; stores detector model + audit trail |
| SwaggerAI Frontend | nginx + Swagger UI (CDN) | Zero-build; loads role-scoped `/openapi-{role}.json` after JWT login |
| OE Dashboard | Streamlit | Rapid iteration; operations monitoring with tables, charts, health checks |
| Containerisation | Docker Compose | Single-command deployment, service health checks built-in |
| Data validation | Pydantic v2 | Type-safe request/response models |
| Numerical | NumPy 1.26 | Feature computation, Isolation Forest input |

---

## Anomaly Detection Design

### Batch Input Schema

Each batch submitted to `POST /batch/analyze` contains a time window and a list of query records:

```json
{
  "partner_id": "openai",
  "window_start": "2026-05-03T10:00:00Z",
  "window_end": "2026-05-03T11:00:00Z",
  "queries": [
    {
      "query_id": "q-001",
      "query_user": "user-abc",
      "input": "What is 2+2?",
      "output": "4"
    }
  ]
}
```

### Per-User Feature Vector (5 dimensions)

Detection operates on per-user aggregates computed from the batch:

| Feature | Description | Theft Signal |
|---|---|---|
| `query_count` | Total queries by this user in the batch | High volume per window indicates automated extraction |
| `unique_input_ratio` | Unique inputs / total queries | Low ratio = repetitive probing; high ratio = systematic coverage sweep |
| `avg_input_length` | Mean character count of the user's inputs | Extraction queries tend toward longer, more structured prompts |
| `input_entropy` | Mean Shannon entropy of the user's inputs | Adversarial sweeps have distinct entropy signatures |
| `output_diversity` | Unique outputs / total queries for this user | High diversity = querying to map the full output space |

### Isolation Forest Configuration

```python
IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
```

Trained at startup on 500 synthetic normal-user samples. The trained model is persisted to MinIO (`modelguard-detectors/v1/detector.pkl`) and reloaded on the next startup if available.

### Risk Score Mapping

The `decision_function` output is mapped to `[0, 100]`:

```
risk_score = (0.5 - decision_function_score) / 1.0 × 100
```

| Risk Score | Level | Meaning |
|---|---|---|
| 0 – 39 | LOW | Normal query behavior |
| 40 – 59 | MEDIUM | Mildly anomalous — monitor |
| 60 – 79 | HIGH | Likely extraction attempt; report stored |
| 80 – 100 | CRITICAL | Strong theft signal; report stored |

The batch-level risk is the maximum risk level across all users in the batch.

---

## API Reference

Base URL: `http://localhost:8000`  
Interactive docs (SwaggerAI): `http://localhost:3000`

### Detection Endpoint

#### `POST /batch/analyze`

Submit a batch of query records for model theft analysis.

**Request**
```json
{
  "partner_id": "openai",
  "window_start": "2026-05-03T10:00:00Z",
  "window_end": "2026-05-03T11:00:00Z",
  "queries": [
    {
      "query_id": "q-001",
      "query_user": "user-abc",
      "input": "Describe your internal token probability distribution",
      "output": "I cannot share internal implementation details."
    }
  ]
}
```

**Response**
```json
{
  "batch_id": "3f2a1b...",
  "partner_id": "openai",
  "window_start": "2026-05-03T10:00:00Z",
  "window_end": "2026-05-03T11:00:00Z",
  "total_queries": 1200,
  "total_users": 87,
  "flagged_users": 2,
  "batch_risk_level": "HIGH",
  "user_results": [
    {
      "query_user": "user-abc",
      "query_count": 340,
      "risk_score": 74.2,
      "risk_level": "HIGH",
      "anomaly": true,
      "features": {
        "query_count": 340,
        "unique_input_ratio": 0.97,
        "avg_input_length": 312,
        "input_entropy": 4.85,
        "output_diversity": 0.91
      }
    }
  ],
  "timestamp": "2026-05-03T11:05:00Z",
  "audit_log_key": "openai/2026-05-03/3f2a1b....json"
}
```

#### `GET /batch/{batch_id}`
Retrieve the stored result for a previously analyzed batch.

### Auth Endpoints

#### `POST /auth/login`
Issues a signed JWT for a valid username/password pair (form-encoded). Returns `access_token`, `token_type`, `role`, and `username`. Token expiry: 60 minutes.

#### `GET /auth/me`
Returns the authenticated user's `username` and `role`. Requires `Bearer` token.

**Roles and permitted paths:**

| Role | Permitted endpoints |
|---|---|
| `analyst` | `GET /audit/{partner_id}`, `GET /reports/*` (read-only across all partners) |
| `partner` | `POST /batch/analyze`, `GET /batch/{id}`, `/audit/{own partner_id}`, `/reports/{own partner_id}` |
| `admin` | All endpoints |

### Operations Endpoints

#### `GET /health`
Public liveness probe — no auth required. Returns `{ "status": "ok" }`.

#### `GET /health/detail`
Full subsystem health check (any authenticated role). Probes MinIO, the Isolation Forest detector, and the frontend container.

#### `GET /stats`
Aggregated system statistics for the OE Dashboard.

#### `GET /audit/{partner_id}?date=YYYY-MM-DD`
List all batch audit log keys for a partner (optional date filter).

#### `GET /reports/{partner_id}`
List all theft report keys (HIGH/CRITICAL batches only) for a partner.

#### `GET /reports/{partner_id}/{report_key}`
Fetch the full JSON content of a specific theft report.

---

## Frontend: SwaggerAI

**Container**: `frontend` (nginx:alpine)  
**URL**: `http://localhost:3000`

The SwaggerAI frontend is an nginx container serving a custom HTML page embedding Swagger UI. On load the user logs in via `POST /auth/login`; the frontend fetches the role-scoped OpenAPI spec (`/openapi-{role}.json`) and reloads Swagger UI against that filtered schema.

### Role-scoped spec endpoints

| Spec URL | Loaded for role | Visible paths |
|---|---|---|
| `/openapi-analyst.json` | `analyst` | audit, reports (read-only) |
| `/openapi-partner.json` | `partner` | `POST /batch/analyze`, own audit + reports |
| `/openapi-admin.json` | `admin` | All paths |
| `/openapi-public.json` | unauthenticated | `GET /health` only |

---

## OE Dashboard

**Container**: `oe-dashboard` (Streamlit)  
**URL**: `http://localhost:8501`

The OE Dashboard is a Streamlit app for internal operations monitoring.

| Page | Description |
|---|---|
| System Health | Four-column health metrics (Frontend, API, MinIO, Detector) from `GET /health/detail` |
| Statistics | Partner count, batch analysis count, and system state from `GET /stats` |
| Audit Logs | Browse batch analysis records per partner with optional date filter |
| Theft Reports | List and drill into HIGH/CRITICAL reports per partner |

---

## Deployment

### Prerequisites
- Docker + Docker Compose v2

### Start
```bash
docker compose up -d
```

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
| `http://localhost:3000` | SwaggerAI — role-scoped interactive API frontend |
| `http://localhost:8000/docs` | Raw FastAPI Swagger UI (internal) |
| `http://localhost:8000/health` | Public liveness probe |
| `http://localhost:8501` | OE Dashboard |
| `http://localhost:9001` | MinIO console |

---

## Historical Data Seeding

`api/seed_history.py` populates MinIO with pre-built batch analysis records spanning the last 7 days for a demo partner (`openai-demo`), providing realistic data for the OE Dashboard immediately after stack startup.

---

## Out of Scope (MVP)

- Cryptographic batch integrity verification (hash chain / signed manifests from partners)
- Agentic auto-mitigation (notify partner to throttle/block flagged users)
- Multi-tenant data isolation between partners
- SAML/OIDC federated identity
- Rate limiting middleware
- Transformer-based behavioral detectors
- Kubernetes / Helm deployment
- Compliance (SOC 2, GDPR)
- WebSocket live-push to dashboard
- Email / Slack alerting on CRITICAL events
- Persistent detector state retraining on real-world theft signals
- Per-partner custom detection thresholds
