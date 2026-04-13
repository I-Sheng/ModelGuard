# ModelGuard Dashboard

Streamlit-based frontend for ModelGuard AI. Provides a visual interface for submitting queries for analysis, registering models, and browsing audit logs and attack reports stored in MinIO — all via the ModelGuard API.

---

## Purpose

The dashboard is an operator-facing UI. It does **not** connect to MinIO directly — it talks exclusively to the FastAPI backend at `http://api:8000`. The backend handles all storage. This keeps the dashboard stateless and simple.

---

## Running (container only)

Start via Docker Compose from the repo root:

```bash
docker compose up --build dashboard
```

The dashboard is available at **http://localhost:8501**.

The container mounts `./dashboard` as a volume so edits to `app.py` are picked up automatically by Streamlit's built-in file watcher.

---

## Pages

### Dashboard (home)

Overview of the system state:

- Count of registered models (fetched from `GET /models`)
- Detection engine and storage backend info
- Risk level reference chart (LOW → CRITICAL thresholds)

---

### Analyze Query

Submit a query text for real-time anomaly scoring.

**Fields:**

| Field | Description |
|---|---|
| Model ID | Which model is being queried |
| Client ID | Optional caller identifier |
| Query Text | The raw query / prompt to analyze |

**What happens:**
1. Sends `POST /analyze` to the API
2. Displays risk level (color-coded), risk score, anomaly flag
3. Shows the extracted feature vector
4. Shows the MinIO bucket and object key where the audit record was stored

Use this page to manually test how ModelGuard classifies different query styles — for example, a normal conversational query vs. a systematic token-probability extraction attempt.

---

### Register Model

Register a new model under protection.

**Fields:** Model ID, Name, Version, Description, Owner

Sends `POST /models/register`. The API stores the metadata as a JSON object in the `modelguard-models` MinIO bucket. The resulting bucket key is displayed on success.

---

### Audit Logs

Browse query audit records for a model.

- Enter a Model ID and optionally a date (`YYYY-MM-DD`) to filter
- Fetches `GET /audit/{model_id}?date=...`
- Displays a table of object keys, sizes, and timestamps

Each row corresponds to one analyzed query. The key encodes the model, date, and query UUID, so you can cross-reference with the Analyze Query results.

---

### Attack Reports

Browse HIGH/CRITICAL attack reports for a model.

- Enter a Model ID and click **Fetch Reports**
- Fetches `GET /reports/{model_id}`
- Select any report from the list to view its full JSON content inline

Only queries flagged as `HIGH` or `CRITICAL` produce a report. This page is where you investigate confirmed attack attempts.

---

## Sidebar

The sidebar is persistent across all pages and shows:

- App name and version
- Navigation radio buttons
- **System Health** expander — polls `GET /health` and shows the API, MinIO, and detector status

If the API is unreachable, the health expander shows a warning and all pages will display errors when they try to fetch data.

---

## How It Talks to the API

All network calls use `httpx` (synchronous) with a 5-second timeout for GET requests and 10-second timeout for POST requests. Errors are caught and displayed as Streamlit error banners rather than crashing the page.

The API base URL is hardcoded to `http://api:8000` (the Docker Compose service name). If you run the dashboard outside of Docker Compose, set the `API_BASE` variable in `app.py` to point at the correct host.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Full Streamlit application — all pages and helpers |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build instructions (Python 3.11-slim base) |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | 1.39.0 | UI framework |
| `httpx` | 0.27.2 | HTTP client for API calls |
| `pandas` | 2.2.3 | Tabular data display |
| `plotly` | 5.24.1 | Risk level bar chart |
