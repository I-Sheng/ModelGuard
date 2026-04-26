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
| `total_models` | integer | "Registered Models" metric |
| `detector` | string | "Detection Engine" metric |
| `minio` | string | "MinIO" metric |

---

## `GET /models`

Used by: Statistics page "Registered Models" table.

| Field | Type | Dashboard use |
|---|---|---|
| `models` | array of objects | Rendered as a dataframe |

---

## `GET /audit/{model_id}`

Used by: Audit Logs page.

Query params: `date` (optional, `YYYY-MM-DD`).

| Field | Type | Dashboard use |
|---|---|---|
| `audit_logs` | array of objects | Rendered as a dataframe; count shown in success message |

---

## `GET /reports/{model_id}`

Used by: Attack Reports page (report list).

| Field | Type | Dashboard use |
|---|---|---|
| `attack_reports` | array of objects | Rendered as a dataframe; count shown in warning |
| `attack_reports[].key` | string | Populates the "Inspect report" selectbox |

---

## `GET /reports/{model_id}/{report_key}`

Used by: Attack Reports page (report detail).

| Field | Type | Dashboard use |
|---|---|---|
| `risk_level` | string | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` — colored label |
| `risk_score` | number | "Risk Score / 100" metric |
| `anomaly` | boolean | "Anomaly Yes/No" metric |
| `query_id` | string | "Query ID" metric (first 8 chars) |
| `features` | object | "Feature Vector" JSON block |
