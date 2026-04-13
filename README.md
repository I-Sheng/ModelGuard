# ModelGuard AI

ModelGuard AI detects model theft attacks in real-time by analyzing API query patterns and behavioral anomalies, protecting enterprise ML models from IP extraction and poisoning.

> **Prototype branch:** `dev` — MinIO + Docker Compose stack  
> **Version:** 0.1.0-oss

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
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose Stack                    │
│                                                             │
│  ┌──────────────┐    ┌───────────────┐    ┌─────────────┐  │
│  │  Streamlit   │───▶│  FastAPI API  │───▶│    MinIO    │  │
│  │  Dashboard   │    │  :8000        │    │  :9000/9001 │  │
│  │  :8501       │    │               │    │             │  │
│  └──────────────┘    └───────┬───────┘    └──────┬──────┘  │
│                              │                   │          │
│                    Isolation Forest        3 Buckets:       │
│                    anomaly detector        models           │
│                    (in-process)            auditlog         │
│                                            reports          │
└─────────────────────────────────────────────────────────────┘
```

| Service | Image | Port | Role |
|---|---|---|---|
| `minio` | `minio/minio:latest` | 9000 (API), 9001 (Console) | Object storage |
| `minio-init` | `minio/mc:latest` | — | One-shot bucket bootstrap |
| `api` | built from `./api` | 8000 | Detection backend |
| `dashboard` | built from `./dashboard` | 8501 | Streamlit frontend |

---

## Quick Start

> **No local installs required.** Everything runs inside containers.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose`)

### 1. Clone and start

```bash
git clone git@github.com:I-Sheng/ModelGuard.git
cd ModelGuard
git checkout dev

docker compose up --build
```

First run pulls images and builds the two custom containers. Subsequent runs are fast.

### 2. Open the services

| URL | What |
|---|---|
| http://localhost:8501 | Streamlit dashboard |
| http://localhost:8000/docs | FastAPI interactive docs (Swagger UI) |
| http://localhost:9001 | MinIO Console — username/password: `minioadmin` |

### 3. Run the smoke-test

```bash
bash demo.sh
```

This registers a model, sends a normal query, sends a suspicious extraction query, then lists the resulting audit logs and attack reports from MinIO.

### 4. Tear down

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
├── docker-compose.yml      # Orchestrates all services
├── .env.example            # Environment variable template
├── demo.sh                 # Smoke-test script
├── api/                    # FastAPI detection backend
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── dashboard/              # Streamlit frontend
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── images/
│   └── Architecture_Diagram.png
├── README.md               # ← you are here
└── Technical_Design.md
```

See each subdirectory for its own README:

- [`api/README.md`](api/README.md) — detection engine, endpoints, MinIO integration
- [`dashboard/README.md`](dashboard/README.md) — Streamlit UI, pages, how it talks to the API

---

## MinIO Buckets

| Bucket | Content | Written by |
|---|---|---|
| `modelguard-models` | Model metadata JSON + binary artifacts | `POST /models/register`, `POST /models/{id}/upload` |
| `modelguard-auditlog` | Every query audit record | `POST /analyze` (always) |
| `modelguard-reports` | Attack reports for HIGH/CRITICAL events | `POST /analyze` (background task) |

Object keys follow a predictable path structure so records are browsable in the MinIO Console without any extra tooling.

---

## Detection Method

The prototype uses an **Isolation Forest** trained on synthetic normal-traffic data. It scores each query on four features:

| Feature | Description |
|---|---|
| `query_length` | Character count of the raw query |
| `unique_token_ratio` | Distinct words ÷ total words (low = repetitive probing) |
| `entropy` | Shannon entropy of the query string |
| `request_rate_1m` | Queries seen in the last 60 seconds from this process |

The raw Isolation Forest decision score is mapped linearly to a 0–100 risk scale. Thresholds:

| Score | Level |
|---|---|
| 0 – 39 | LOW |
| 40 – 59 | MEDIUM |
| 60 – 79 | HIGH |
| 80 – 100 | CRITICAL |

---

## Roadmap

See [`Technical_Design.md`](Technical_Design.md) for the full MVP scope. Planned next steps:

- [ ] Persistent query history (replace in-memory window with Redis or TimescaleDB)
- [ ] Per-client rate tracking across requests
- [ ] Webhook / Slack alerting on CRITICAL events
- [ ] React frontend (replacing Streamlit)
- [ ] Real model artifact scanning and checksum validation
