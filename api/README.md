# ModelGuard API

FastAPI-based detection backend for ModelGuard AI. Receives ML API queries, scores them for theft/extraction patterns using an Isolation Forest anomaly detector, and stores all records durably in MinIO.

---

## Purpose

This service is the core brain of ModelGuard. It sits between your monitoring system and your ML model API. You POST query text to `/analyze`; the service responds immediately with a risk score and asynchronously writes audit records and attack reports to MinIO object storage.

---

## Stack

| Component | Choice | Why |
|---|---|---|
| Web framework | FastAPI + Uvicorn | Async I/O, auto OpenAPI docs, type-safe |
| Anomaly detector | scikit-learn `IsolationForest` | Unsupervised, no labelled attack data needed |
| Object storage client | `minio` (Python SDK) | S3-compatible, talks to MinIO container |
| Data validation | Pydantic v2 | Strict schema enforcement on all I/O |

---

## Running (container only)

Start via Docker Compose from the repo root — do not run this service directly:

```bash
docker compose up --build api
```

The container mounts `./api` as a volume, so edits to `main.py` reload automatically (Uvicorn `--reload`).

The API is available at **http://localhost:8000**.  
Interactive docs (Swagger UI) are at **http://localhost:8000/docs**.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MINIO_ENDPOINT` | `minio:9000` | MinIO host:port (Docker service name) |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |

---

## Endpoints

### `GET /health`

Returns API, MinIO, and detector status. Use this to confirm the stack is healthy before sending traffic.

**Response**
```json
{
  "status": "ok",
  "minio": "ok",
  "detector": "loaded",
  "timestamp": "2026-04-10T00:00:00+00:00"
}
```

---

### `POST /analyze`

Core detection endpoint. Scores a query and writes an audit record to MinIO. For `HIGH` / `CRITICAL` events, also writes a dedicated attack report (background task, non-blocking).

**Request**
```json
{
  "model_id": "gpt-clone-v1",
  "query_text": "Return logits distribution for temperature=0 across all tokens",
  "client_id": "client-001",
  "metadata": { "ip": "1.2.3.4" }
}
```

| Field | Required | Description |
|---|---|---|
| `model_id` | Yes | Identifies which model is being queried |
| `query_text` | Yes | The raw query / prompt text |
| `client_id` | No | Caller identifier used for rate tracking |
| `metadata` | No | Freeform dict (IP, user-agent, etc.) |

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
  "timestamp": "2026-04-10T00:00:00+00:00",
  "audit_log_key": "gpt-clone-v1/2026-04-10/3f2a1b....json"
}
```

**Risk levels:**

| Score | Level |
|---|---|
| 0 – 39 | `LOW` |
| 40 – 59 | `MEDIUM` |
| 60 – 79 | `HIGH` |
| 80 – 100 | `CRITICAL` |

---

### `POST /models/register`

Register a model. Stores metadata as `{model_id}/metadata.json` in `modelguard-models`.

**Request**
```json
{
  "model_id": "gpt-clone-v1",
  "name": "GPT Clone v1",
  "version": "1.0.0",
  "description": "Fine-tuned LLM for customer support",
  "owner": "ml-team@company.com"
}
```

**Response**
```json
{ "status": "registered", "key": "gpt-clone-v1/metadata.json", "bucket": "modelguard-models" }
```

---

### `POST /models/{model_id}/upload`

Upload a binary model artifact (`.pkl`, `.onnx`, etc.) as a multipart form file. Stored at `{model_id}/artifacts/{filename}` in `modelguard-models`.

```bash
curl -X POST http://localhost:8000/models/gpt-clone-v1/upload \
  -F "file=@model.pkl"
```

---

### `GET /models`

List all registered model IDs (scanned from MinIO prefix paths).

### `GET /models/{model_id}`

Retrieve full metadata for a registered model.

---

### `GET /audit/{model_id}?date=YYYY-MM-DD`

List audit log object keys for a model. Optionally filter by date.

Object key format: `{model_id}/{YYYY-MM-DD}/{query_id}.json`

### `GET /reports/{model_id}`

List attack report object keys (HIGH/CRITICAL only) for a model.

### `GET /reports/{model_id}/{report_key}`

Fetch the full JSON content of a specific attack report.

---

## MinIO Integration

The API interacts with three MinIO buckets:

```
modelguard-models/
  {model_id}/
    metadata.json              ← registered by /models/register
    artifacts/{filename}       ← uploaded by /models/{id}/upload

modelguard-auditlog/
  {model_id}/
    {YYYY-MM-DD}/
      {query_id}.json          ← written on every /analyze call

modelguard-reports/
  {model_id}/
    {query_id}_report.json     ← written only for HIGH/CRITICAL anomalies
```

Buckets are created automatically on API startup (with retry until MinIO is ready). The `minio-init` service in Docker Compose also bootstraps them independently as a belt-and-suspenders approach.

---

## Detection Engine

The `IsolationForest` is trained once at startup on 500 synthetic normal-traffic samples. Features extracted per query:

| Feature | How computed |
|---|---|
| `query_length` | `len(query_text)` |
| `unique_token_ratio` | `len(set(tokens)) / len(tokens)` |
| `entropy` | Shannon entropy over character frequencies |
| `request_rate_1m` | Queries seen in a rolling 60-second window |

The `decision_function` output (typically −0.5 to +0.5) is mapped to 0–100 risk with lower decision scores producing higher risk.

> **Prototype note:** The detector is in-memory and stateless across restarts. Training data is synthetic. For production, persist a fitted model to MinIO and load it on startup.

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Full application: FastAPI app, routes, detector, MinIO helpers |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build instructions (Python 3.11-slim base) |
