# Metrics Specification — ModelGuard AI

This document defines the data fields the OE Dashboard reads from the ModelGuard API.

> OE Dashboard source: [`oe-dashboard/app.py`](oe-dashboard/app.py)

---

## `GET /health/detail`

Used by: Sidebar "Live System Health", System Health page.

| Field | Type | Values | Dashboard use |
|---|---|---|---|
| `status` | string | `"ok"` / other | API Status metric; `api_ok` check |
| `minio` | string | `"ok"` / other | MinIO metric; `minio_ok` check |
| `detector` | string | `"loaded"` / `"not loaded"` | Detection Engine metric; `det_ok` check |
| `frontend` | string | `"ok"` / other | Frontend metric; `frontend_ok` check |

---

## `GET /stats`

Used by: Statistics page.

| Field | Type | Dashboard use |
|---|---|---|
| `total_partners` | integer | "Registered Partners" metric |
| `total_batches_analyzed` | integer | "Batches Analyzed" metric |
| `detector` | string | "Detection Engine" metric |
| `minio` | string | "MinIO" metric |

---

## `GET /audit/{partner_id}`

Used by: Audit Logs page.

Query params: `date` (optional, `YYYY-MM-DD`).

| Field | Type | Dashboard use |
|---|---|---|
| `audit_logs` | array of objects | Rendered as a dataframe; count shown in success message |

Each audit log object includes:

| Field | Type | Description |
|---|---|---|
| `batch_id` | string | Unique identifier for the analyzed batch |
| `partner_id` | string | Partner who submitted the batch |
| `window_start` | string (ISO 8601) | Start of the query window |
| `window_end` | string (ISO 8601) | End of the query window |
| `total_queries` | integer | Total query records in the batch |
| `total_users` | integer | Distinct users in the batch |
| `flagged_users` | integer | Users scored HIGH or CRITICAL |
| `batch_risk_level` | string | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `timestamp` | string (ISO 8601) | Time the analysis was completed |

---

## `GET /reports/{partner_id}`

Used by: Theft Reports page (report list).

| Field | Type | Dashboard use |
|---|---|---|
| `theft_reports` | array of objects | Rendered as a dataframe; count shown in warning |
| `theft_reports[].key` | string | Populates the "Inspect report" selectbox |

---

## `GET /reports/{partner_id}/{report_key}`

Used by: Theft Reports page (report detail).

| Field | Type | Dashboard use |
|---|---|---|
| `batch_risk_level` | string | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` — colored label |
| `flagged_users` | integer | "Flagged Users" metric |
| `total_queries` | integer | "Total Queries in Batch" metric |
| `batch_id` | string | "Batch ID" metric (first 8 chars) |
| `user_results` | array | Per-user risk breakdown table |
| `user_results[].query_user` | string | User identifier |
| `user_results[].risk_score` | number | "Risk Score / 100" per user |
| `user_results[].risk_level` | string | Per-user risk level label |
| `user_results[].features` | object | "Feature Vector" JSON block |
