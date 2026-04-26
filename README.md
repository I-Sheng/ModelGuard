# ModelGuard AI

ModelGuard AI detects model theft attacks in real-time by analyzing API query patterns and behavioral anomalies, protecting enterprise ML models from IP extraction and poisoning.

> **Version:** 0.2.0-oss

---

## What It Does

When a client queries your deployed ML model, ModelGuard sits in the detection path and scores every request for signs of:

- **Model extraction** — systematic querying designed to reconstruct model weights
- **Membership inference** — probing for training data membership signals
- **Anomalous request bursts** — high-rate automated sweeps of the model API

Each query is scored 0–100 and classified as `LOW / MEDIUM / HIGH / CRITICAL`. All audit records are stored durably in MinIO (S3-compatible object storage). `HIGH` and `CRITICAL` events also produce a dedicated attack report.

Access to the API is controlled by **JWT-based role-based access control**. Clients log in once at `POST /auth/login` and use the returned Bearer token on all subsequent calls. The frontend loads a role-scoped OpenAPI spec so each user only sees the endpoints they are permitted to call.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose Stack                             │
│                                                                           │
│  ┌──────────────────┐  1. POST /auth/login      ┌────────────────────┐  │
│  │  SwaggerAI       │ ────────────────────────► │                    │  │
│  │  Frontend        │  2. GET /openapi-{role}   │   Backend API      │  │
│  │  nginx :3000     │ ◄──────────────────────── │   FastAPI :8000    │  │
│  │                  │  3. Bearer JWT on all      │                    │  │
│  │  Role-scoped     │     API calls             │  ● JWT Auth + RBAC │  │
│  │  Swagger UI      │ ────────────────────────► │  ● Isolation Forest│  │
│  └──────────────────┘                           │  ● MinIO writes    │  │
│                                                  └────────┬───────────┘  │
│  ┌──────────────────┐  Bearer JWT (admin)                │ S3 API        │
│  │  OE Dashboard    │ ────────────────────────►          │               │
│  │  Streamlit :8501 │  Auto-login on startup    ┌────────▼───────────┐  │
│  │                  │  /health/detail            │  MinIO             │  │
│  │  Health │ Stats  │  /audit/{model_id}         │  :9000  S3 API     │  │
│  │  Audit  │ Reports│  /reports/{model_id}       │  :9001  Console    │  │
│  └──────────────────┘                            │                    │  │
│                                                   │  modelguard-models │  │
│  ┌──────────────────┐  one-shot bucket creation  │  modelguard-audit  │  │
│  │  minio-init      │ ────────────────────────►  │  modelguard-reports│  │
│  └──────────────────┘                            └────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Detection Pipeline

Every call to `POST /analyze` or `POST /predict` runs the same pipeline:

```
Incoming query
     │
     ├─ 1. JWT verification + role check
     │
     ├─ 2. Feature extraction
     │        query_length · unique_token_ratio · shannon_entropy · request_rate_1m
     │
     ├─ 3. Isolation Forest inference
     │        → anomaly flag · decision_function score → risk score 0–100
     │        → risk level  LOW / MEDIUM / HIGH / CRITICAL
     │
     ├─ 4. Audit record → MinIO  modelguard-auditlog  (every request)
     │
     ├─ 5. Attack report → MinIO  modelguard-reports  (HIGH / CRITICAL only, background)
     │
     └─ 6. JSON response returned to caller
```

### Containers

| Container | Port | Role |
|---|---|---|
| `backend` | 8000 | FastAPI detection engine — JWT auth + RBAC, Isolation Forest, MinIO writes, all API endpoints |
| `frontend` | 3000 | SwaggerAI — serves role-scoped OpenAPI spec after JWT login; proxies API calls |
| `oe-dashboard` | 8501 | Operations/Engineering dashboard — auto-logins as admin; health, stats, audit logs, reports |
| `minio` | 9000 / 9001 | S3-compatible object storage for models, audit logs, and attack reports |
| `minio-init` | — | One-shot bootstrap — creates the three MinIO buckets, then exits |

---

## Authentication

All endpoints except `GET /health` and `POST /auth/login` require a `Bearer` JWT token.

### 1. Log in

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -d "username=ml_user&password=ml_password" | jq .
# → { "access_token": "...", "token_type": "bearer", "role": "ml_user", "username": "ml_user" }
```

Use the returned `access_token` as `Authorization: Bearer <token>` on all subsequent requests.

### 2. Demo users

| Username | Password | Role | Permitted endpoints |
|---|---|---|---|
| `ml_user` | `ml_password` | `ml_user` | `GET /models`, `POST /predict` |
| `customer1` | `customer_password` | `customer` | ml_user paths + `/models/{id}/upload`, `/audit/{id}`, `/reports/*` |
| `admin` | `admin_password` | `admin` | All endpoints |

> **Production note:** Replace demo credentials via environment variables and set a strong `JWT_SECRET_KEY`.

### 3. Role-scoped OpenAPI specs

The frontend fetches a filtered spec after login so users only see their permitted paths:

| Endpoint | Served to |
|---|---|
| `/openapi-ml.json` | `ml_user` |
| `/openapi-customer.json` | `customer` |
| `/openapi-admin.json` | `admin` |
| `/openapi-public.json` | unauthenticated (only `/health`) |

---

## Quick Start

> **No local installs required.** Everything runs inside containers.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose`)

### 1. Clone and start

```bash
git clone git@github.com:I-Sheng/ModelGuard.git
cd ModelGuard
docker compose up --build
```

First run pulls images and builds the three custom containers. Subsequent runs are fast.

### 2. Open the services

| URL | What |
|---|---|
| http://localhost:3000 | SwaggerAI frontend — submit queries, register models |
| http://localhost:8501 | OE Dashboard — health, audit logs, attack reports |
| http://localhost:8000/docs | Raw FastAPI Swagger UI (internal dev) |
| http://localhost:9001 | MinIO Console — username/password: `minioadmin` |

### 3. Seed demo data

```bash
docker compose exec backend python seed_history.py
```

### 4. Run the smoke-test

```bash
bash demo.sh
```

Registers a model, sends a normal query, sends a suspicious extraction query, then lists audit logs and attack reports.

### 5. Tear down

```bash
docker compose down          # stop containers, keep MinIO data volume
docker compose down -v       # stop containers AND delete MinIO data
```

---

## Configuration

Copy `.env.example` to `.env` to override defaults:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `MINIO_ROOT_USER` | `minioadmin` | MinIO root username |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO root password |
| `MINIO_ENDPOINT` | `minio:9000` | Internal MinIO endpoint (service name) |
| `JWT_SECRET_KEY` | `modelguard-dev-secret-change-in-production` | HS256 signing secret — **change this in production** |
| `OE_ADMIN_USER` | `admin` | Username the OE dashboard uses to authenticate with the backend |
| `OE_ADMIN_PASSWORD` | `admin_password` | Password for `OE_ADMIN_USER` |

---

## Project Structure

```
ModelGuard/
├── docker-compose.yml        # Orchestrates all five services
├── .env.example              # Environment variable template
├── demo.sh                   # Smoke-test script
├── api/                      # FastAPI detection backend
│   ├── Dockerfile
│   ├── main.py
│   ├── seed_history.py
│   └── requirements.txt
├── frontend/                 # SwaggerAI frontend (nginx + Swagger UI)
│   ├── Dockerfile
│   ├── index.html
│   └── nginx.conf
├── oe-dashboard/             # Operations/Engineering dashboard (Streamlit)
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── images/
│   └── Architecture_Diagram.png
├── README.md
└── docs/
```

---

## MinIO Buckets

| Bucket | Content | Written by |
|---|---|---|
| `modelguard-models` | Model metadata JSON + binary artifacts | `POST /models/register`, `POST /models/{id}/upload` |
| `modelguard-auditlog` | Every query audit record | `POST /analyze`, `POST /predict` (always) |
| `modelguard-reports` | Attack reports for HIGH/CRITICAL events | `POST /analyze`, `POST /predict` (background task) |

---

## API Endpoints

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| `POST` | `/auth/login` | No | — | Issue a JWT for a valid username/password |
| `GET` | `/auth/me` | Yes | any | Return the current user's identity and role |
| `GET` | `/health` | No | — | Public liveness probe — returns `{"status":"ok"}` |
| `GET` | `/health/detail` | Yes | any | Full health: API, MinIO, Isolation Forest, Frontend |
| `GET` | `/stats` | No | — | Aggregated system stats for the OE Dashboard |
| `POST` | `/models/register` | Yes | admin | Register a model (stores metadata in MinIO) |
| `GET` | `/models` | Yes | any | List all registered models |
| `GET` | `/models/{id}` | No | — | Retrieve model metadata |
| `POST` | `/models/{id}/upload` | Yes | customer, admin | Upload a binary model artifact |
| `POST` | `/analyze` | Yes | any | Analyze a query for theft/extraction patterns |
| `POST` | `/predict` | Yes | any | Run mock sentiment inference + anomaly detection |
| `GET` | `/audit/{model_id}` | Yes | customer, admin | List audit log entries (optionally filtered by date) |
| `GET` | `/reports/{model_id}` | Yes | customer, admin | List HIGH/CRITICAL attack reports |
| `GET` | `/reports/{model_id}/{key}` | Yes | customer, admin | Fetch full content of an attack report |

---

## Detection Method

An **Isolation Forest** trained on synthetic normal-traffic data scores each query on four features:

| Feature | Description |
|---|---|
| `query_length` | Character count of the raw query |
| `unique_token_ratio` | Distinct words / total words (low = repetitive probing) |
| `entropy` | Shannon entropy of the query string |
| `request_rate_1m` | Queries seen in the last 60 seconds from this process |

Risk thresholds:

| Score | Level |
|---|---|
| 0 – 39 | LOW |
| 40 – 59 | MEDIUM |
| 60 – 79 | HIGH |
| 80 – 100 | CRITICAL |

---

## Roadmap

See [`Technical_Design.md`](docs/Technical_Design.md) for the full design. Planned next steps:

- [ ] Persistent query history (replace in-memory window with Redis or TimescaleDB)
- [ ] Per-client rate tracking across requests
- [ ] Webhook / Slack alerting on CRITICAL events
- [ ] Real model artifact scanning and checksum validation

---

## Changelog

### 0.2.0-oss

- **JWT auth + RBAC** — `POST /auth/login` issues signed tokens; all non-public endpoints require `Bearer` auth. Three built-in roles: `ml_user`, `customer`, `admin`.
- **Role-scoped OpenAPI specs** — frontend loads `/openapi-ml.json`, `/openapi-customer.json`, or `/openapi-admin.json` after login so each role sees only its permitted paths.
- **`/health` split** — `GET /health` is now a public liveness probe returning `{"status":"ok"}`. Full subsystem status (MinIO, Isolation Forest, Frontend) moved to `GET /health/detail` (auth required).
- **Frontend health check** — `/health/detail` now probes the frontend container and returns its status.
- **`POST /predict`** — new endpoint that runs the mock sentiment classifier and ModelGuard anomaly detection in a single call, returning both the model prediction and a risk assessment.
- **OE Dashboard auth** — the dashboard authenticates as `admin` on startup using `OE_ADMIN_USER` / `OE_ADMIN_PASSWORD` environment variables. Health indicators reordered: Frontend → API → MinIO → Detector.
