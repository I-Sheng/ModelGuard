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

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                          │
│                                                                      │
│  ┌────────────────┐  REST/JSON  ┌──────────────────────────────┐   │
│  │  SwaggerAI     │ ──────────► │  Backend API                 │   │
│  │  Frontend      │             │  FastAPI + Uvicorn :8000      │   │
│  │  nginx :3000   │             │  Isolation Forest (in-proc)  │   │
│  └────────────────┘             └──────────────┬───────────────┘   │
│                                                 │ S3 API             │
│  ┌────────────────┐  REST/JSON  ┌──────────────▼───────────────┐   │
│  │  OE Dashboard  │ ──────────► │  MinIO                       │   │
│  │  Streamlit     │             │  S3-compatible object store  │   │
│  │  :8501         │             │  :9000 (API) / :9001 (UI)    │   │
│  └────────────────┘             └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

| Container | Port | Role |
|---|---|---|
| `backend` | 8000 | FastAPI detection engine — Isolation Forest, MinIO writes, all API endpoints |
| `frontend` | 3000 | SwaggerAI — OpenAPI-driven UI for model queries and registration |
| `oe-dashboard` | 8501 | Operations/Engineering dashboard — health, stats, audit logs, reports |
| `minio` | 9000 / 9001 | S3-compatible object storage |
| `minio-init` | — | One-shot bucket bootstrap |

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
| `MINIO_ENDPOINT` | `minio:9000` | Internal endpoint (service name) |

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
└── Technical_Design.md
```

---

## MinIO Buckets

| Bucket | Content | Written by |
|---|---|---|
| `modelguard-models` | Model metadata JSON + binary artifacts | `POST /models/register`, `POST /models/{id}/upload` |
| `modelguard-auditlog` | Every query audit record | `POST /analyze`, `POST /predict` (always) |
| `modelguard-reports` | Attack reports for HIGH/CRITICAL events | `POST /analyze`, `POST /predict` (background task) |

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

See [`Technical_Design.md`](Technical_Design.md) for the full design. Planned next steps:

- [ ] Persistent query history (replace in-memory window with Redis or TimescaleDB)
- [ ] Per-client rate tracking across requests
- [ ] Webhook / Slack alerting on CRITICAL events
- [ ] Real model artifact scanning and checksum validation
- [ ] Enterprise auth (API keys / JWT)
