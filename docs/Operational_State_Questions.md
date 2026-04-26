# Operational State Questions — ModelGuard AI

This document lists the questions an operator must be able to answer **immediately** when asked about the operational state of ModelGuard AI. Each question maps to a specific data source so the answer is never more than one click away on the OE Dashboard.

> OE Dashboard source: [`oe-dashboard/app.py`](oe-dashboard/app.py)

---

## 1. Service Availability

| # | Question | Where to look | Healthy answer |
|---|---|---|---|
| 1.1 | Is the backend API up and responding? | OE Dashboard → System Health → **API Status** | `OK` |
| 1.2 | Is the SwaggerAI frontend reachable by users? | OE Dashboard → System Health → **Frontend** | `OK` |
| 1.3 | Is MinIO storage reachable and accepting requests? | OE Dashboard → System Health → **MinIO** | `OK` |
| 1.4 | Is the Isolation Forest detector loaded and ready to score queries? | OE Dashboard → System Health → **Detection Engine** | `LOADED` |
| 1.5 | Are all four subsystems healthy right now? | OE Dashboard → sidebar **Live System Health** expander | All four show ✅ |

**API source:** `GET /health/detail` (requires auth)

---

## 2. Detection Activity

| # | Question | Where to look | Healthy answer |
|---|---|---|---|
| 2.1 | How many queries have been analyzed today? | OE Dashboard → Audit Logs → fetch by today's date | Count of returned rows |
| 2.2 | Are there any active HIGH or CRITICAL alerts right now? | OE Dashboard → Attack Reports → fetch for each registered model | Zero new reports since last check |
| 2.3 | What is the current request rate (queries/min)? | `request_rate_1m` field in any recent audit log entry | Within normal baseline (< 10 req/min) |
| 2.4 | Which models are receiving the most suspicious queries? | OE Dashboard → Attack Reports → group by `model_id` | No single model dominating |
| 2.5 | What is the risk-level distribution (LOW/MEDIUM/HIGH/CRITICAL) over the last 24 hours? | OE Dashboard → Audit Logs → scan `risk_level` column | Majority LOW, zero CRITICAL |

---

## 3. Storage Health

| # | Question | Where to look | Healthy answer |
|---|---|---|---|
| 3.1 | Is MinIO writing audit logs successfully? | OE Dashboard → Audit Logs → fetch recent entries | Recent entries present with current timestamps |
| 3.2 | Are attack reports being generated for HIGH/CRITICAL events? | OE Dashboard → Attack Reports | Reports exist for any known HIGH/CRITICAL events |
| 3.3 | How many models are currently registered? | OE Dashboard → Statistics → **Registered Models** | Expected count matches known registrations |
| 3.4 | Is MinIO storage capacity within limits? | MinIO Console (`http://localhost:9001`) → Buckets | No bucket at capacity warning |

**API source:** `GET /stats`, `GET /audit/{model_id}`, `GET /reports/{model_id}`

---

## 4. Security Events

| # | Question | Where to look | Healthy answer |
|---|---|---|---|
| 4.1 | How many HIGH/CRITICAL events in the last 24 hours? | OE Dashboard → Attack Reports → count rows with today's date | Zero or within expected noise floor |
| 4.2 | Is there an ongoing extraction attack against any model right now? | OE Dashboard → Attack Reports → sort by `last_modified` descending | No report in the last 5 minutes |
| 4.3 | Which `client_id` is generating the most suspicious queries? | OE Dashboard → Audit Logs → inspect `client_id` in recent HIGH rows | No single client_id dominating |
| 4.4 | What were the feature values on the last CRITICAL event? | OE Dashboard → Attack Reports → select report → **Feature Vector** section | N/A — review `query_length`, `unique_token_ratio`, `entropy`, `request_rate_1m` |
| 4.5 | Has any model been targeted by repeated extraction queries? | OE Dashboard → Audit Logs → filter by model + date → count HIGH/CRITICAL rows | Isolated incidents, not a sustained pattern |

---

## 5. System Performance

| # | Question | Where to look | Healthy answer |
|---|---|---|---|
| 5.1 | Is the anomaly detector returning scores in real time (no queueing)? | Backend logs: `docker compose logs backend` | No timeout errors or scoring delays |
| 5.2 | Are MinIO write errors occurring? | Backend logs: search for `"Failed to store audit log"` | Zero occurrences |
| 5.3 | Is the backend restarting / crash-looping? | `docker compose ps` | `backend` status = `Up`, no recent restarts |
| 5.4 | Is the OE Dashboard itself healthy? | Browser: navigate to `http://localhost:8501` | Dashboard loads; sidebar shows all ✅ |

---

## Quick Reference — Answering in Under 60 Seconds

```
Open http://localhost:8501
├─ Sidebar "Live System Health"   → answers 1.1 – 1.5 (all four subsystems)
├─ Page: System Health            → confirms 1.1 – 1.5 with detail + raw JSON
├─ Page: Statistics               → answers 3.3
├─ Page: Audit Logs               → answers 2.1, 2.3, 2.5, 4.3, 4.5
└─ Page: Attack Reports           → answers 2.2, 4.1, 4.2, 4.4
```
