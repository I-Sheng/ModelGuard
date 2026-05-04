# Oncall Runbook — ModelGuard AI OE Dashboard

This document explains how an on-call engineer uses the ModelGuard OE Dashboard to diagnose and respond to incidents. It assumes the stack is running via `docker compose up`.

> OE Dashboard source: [`oe-dashboard/app.py`](oe-dashboard/app.py)  
> OE Dashboard URL: `http://localhost:8501`  
> Operational state questions: [`Operational_State_Questions.md`](Operational_State_Questions.md)

---

## Start Here — First 60 Seconds

Open `http://localhost:8501`. The sidebar **Live System Health** expander refreshes on every page load and shows four indicators:

```
Frontend  ✅ / ❌
API       ✅ / ❌
MinIO     ✅ / ❌
Detector  ✅ / ❌
```

- **All green** → system is healthy. Proceed to check for theft events (step 4).
- **Any red** → follow the triage tree below.

---

## Triage Tree

### ❌ API is down

The backend container is not responding. Everything else depends on it.

1. Check container status:
   ```bash
   docker compose ps backend
   ```
2. Check for crash loop or startup failure:
   ```bash
   docker compose logs --tail=50 backend
   ```
3. Common causes and fixes:

   | Symptom in logs | Cause | Fix |
   |---|---|---|
   | `Could not connect to MinIO after 10 attempts` | MinIO started late or is down | Restart MinIO first: `docker compose restart minio`, then `docker compose restart backend` |
   | `Address already in use :8000` | Port conflict | Stop the conflicting process, then `docker compose restart backend` |
   | `ModuleNotFoundError` | Dependency missing | `docker compose build backend && docker compose up -d backend` |
   | Container keeps restarting | OOM or unhandled exception | Check `docker stats` for memory; read full logs for traceback |

4. Once backend is back, verify on OE Dashboard → **System Health** that API shows `OK`.

---

### ❌ Frontend is down

Users cannot reach the SwaggerAI UI. ModelGuard detection still works via direct API calls.

1. Check container:
   ```bash
   docker compose ps frontend
   docker compose logs --tail=30 frontend
   ```
2. Reload OE Dashboard — if API is healthy, batch analysis is unaffected. Frontend is stateless; restart is safe:
   ```bash
   docker compose restart frontend
   ```
3. Confirm recovery: OE Dashboard → **System Health** → Frontend = `OK`.

---

### ❌ MinIO is down

Audit logs and theft reports cannot be written. Detection scoring still runs, but all audit records will have `audit_log_key = "minio-unavailable"`.

1. Check MinIO:
   ```bash
   docker compose ps minio
   docker compose logs --tail=30 minio
   ```
2. Try MinIO console: `http://localhost:9001` (credentials: `minioadmin` / `minioadmin`).
3. Restart if needed:
   ```bash
   docker compose restart minio
   ```
   MinIO data is persisted in the `minio_data` Docker volume — a restart does **not** lose data.
4. After MinIO recovers, confirm via OE Dashboard → **System Health** → MinIO = `OK`.
5. **Check for missing audit logs**: OE Dashboard → Audit Logs → fetch for the affected time window. Any batches analyzed during the outage will have no audit record. Note the outage window for the incident report.

---

### ❌ Detector is not loaded

The Isolation Forest is not in memory. Scoring is unavailable; `/batch/analyze` will fail or return incorrect results.

1. Check backend startup logs for the training/load confirmation line:
   ```bash
   docker compose logs backend | grep -E "Isolation Forest trained|detector loaded"
   ```
2. If the detector was not loaded from MinIO, check whether the model file exists:
   ```bash
   docker compose exec backend python -c "
   from minio import Minio; import os
   c = Minio(os.environ['MINIO_ENDPOINT'], ...)
   print(list(c.list_objects('modelguard-detectors')))
   "
   ```
3. If missing, the backend will retrain from synthetic data on the next restart:
   ```bash
   docker compose restart backend
   ```
4. Confirm: OE Dashboard → **System Health** → Detection Engine = `LOADED`.

---

## Scenario 4 — Theft Event Spike

All four subsystems are green, but you received an alert about unusual batch analysis results.

### Step 1 — Check Theft Reports

OE Dashboard → **Theft Reports** → enter a partner ID (e.g. `openai-demo`) → Fetch.

- **No reports**: No HIGH/CRITICAL batches for that partner. Check other partner IDs or widen the Audit Logs search.
- **Reports present**: Note the `window_start` / `window_end` timestamps. Are they clustered (burst campaign) or spread over time (slow extraction)?

### Step 2 — Inspect the Feature Vector

Select a report from the dropdown → expand **User Results** → inspect the per-user feature vectors of flagged users:

| Feature | Theft signal |
|---|---|
| `query_count` > 200 per hour | High-volume automated querying |
| `unique_input_ratio` > 0.95 | Systematic diversity sweep — exploring the full input space |
| `avg_input_length` > 300 chars | Long, structured prompts typical of model-stealing |
| `input_entropy` > 4.5 | High-entropy inputs — varied prompt engineering |
| `output_diversity` > 0.90 | Mapping as many distinct outputs as possible |

A CRITICAL batch with multiple flagged users showing all five signals simultaneously is a strong indicator of an active model extraction campaign.

### Step 3 — Identify the Users

In the **Full Report** section, note the `query_user` values of all flagged users. Share these with the partner so they can cross-reference with their account records.

### Step 4 — Scope the Campaign

OE Dashboard → **Audit Logs** → same partner ID + date range → Fetch.

- Sort by `window_start` (newest first).
- Count consecutive HIGH/CRITICAL batches. A sustained run of HIGH events across multiple hourly windows warrants escalation.

### Step 5 — Escalation Checklist

```
[ ] Confirm partner_id and flagged query_user values
[ ] Screenshot or export the Theft Reports table
[ ] Note the time range, batch count, and flagged user count
[ ] Check if the same query_user appears across multiple batch windows
[ ] Notify the partner to consider throttling or blocking the flagged users
[ ] File an incident report with: partner_id, query_users, time range, risk score range, feature values
```

---

## Scenario 5 — OE Dashboard Itself Is Unreachable

The Streamlit container may have crashed or lost its admin JWT.

1. Check the container:
   ```bash
   docker compose ps oe-dashboard
   docker compose logs --tail=30 oe-dashboard
   ```
2. If the backend is up but the dashboard shows "API error": the cached JWT may have expired (60-minute TTL). Restart the dashboard to force re-login:
   ```bash
   docker compose restart oe-dashboard
   ```
3. If the container is crashed, rebuild:
   ```bash
   docker compose up -d oe-dashboard
   ```
4. As a fallback, query the backend directly:
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
     -d "username=admin&password=admin_password" | jq -r .access_token)
   curl -s -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/health/detail | jq .
   ```

---

## Useful Commands Reference

```bash
# View all container states
docker compose ps

# Tail logs for any service
docker compose logs -f backend
docker compose logs -f oe-dashboard
docker compose logs -f minio

# Restart a single service without affecting others
docker compose restart <service>

# Full restart preserving MinIO data
docker compose down && docker compose up -d

# Wipe everything including MinIO data (destructive — confirm first)
docker compose down -v

# Manual health check (no auth)
curl http://localhost:8000/health

# Detailed health check (requires token)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=admin_password" | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/health/detail | jq .
```

---

## Severity Classification

| Severity | Condition | Response |
|---|---|---|
| **P1 — Critical** | Backend down OR MinIO down with active traffic | Immediate restart; notify team; audit log gap check |
| **P2 — High** | Detector not loaded; frontend down | Restart affected service within 15 minutes |
| **P3 — Medium** | Sustained HIGH/CRITICAL batches (> 3 consecutive windows) from one partner | Investigate flagged users; notify partner |
| **P4 — Low** | Isolated CRITICAL batch; OE Dashboard flaky | Monitor for recurrence; no immediate action required |
