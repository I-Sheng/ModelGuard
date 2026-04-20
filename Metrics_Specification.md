# Metrics Specification — ModelGuard AI

This document defines the metrics ModelGuard must emit for the OE Dashboard (and any future monitoring system) to answer the operational state questions in [`Operational_State_Questions.md`](Operational_State_Questions.md).

> OE Dashboard source: [`oe-dashboard/app.py`](oe-dashboard/app.py)

---

## Metric Naming Convention

All metric names use the prefix `modelguard_` and follow Prometheus naming conventions (`snake_case`, unit suffix where applicable).

---

## 1. Request & Detection Metrics

These are the core throughput and detection signals.

### `modelguard_requests_total`
- **Type:** Counter
- **Labels:** `endpoint` (`/analyze`, `/predict`), `model_id`, `risk_level` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- **Description:** Total number of queries processed, partitioned by outcome.
- **OE Dashboard use:** Powers risk-level distribution charts, per-model query counts.
- **Currently emitted:** Implicitly — every audit log written to MinIO represents one count. No Prometheus endpoint yet.

### `modelguard_anomalies_total`
- **Type:** Counter
- **Labels:** `model_id`, `risk_level`
- **Description:** Total queries classified as anomalous (`anomaly=true`). Subset of `modelguard_requests_total`.
- **OE Dashboard use:** Attack Reports page count, active-alert check.

### `modelguard_request_duration_seconds`
- **Type:** Histogram
- **Labels:** `endpoint`
- **Buckets:** `[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]`
- **Description:** End-to-end latency for `/analyze` and `/predict` (feature extraction + Isolation Forest + MinIO write).
- **OE Dashboard use:** Performance section; p95 latency alert threshold.

### `modelguard_request_rate_1m`
- **Type:** Gauge
- **Labels:** none (process-global, matches the in-memory `_query_window`)
- **Description:** Number of queries seen in the last 60 seconds. This is already computed per request as the `request_rate_1m` feature.
- **OE Dashboard use:** Real-time request rate indicator; burst detection baseline.

---

## 2. Storage Metrics

MinIO write failures are silent in the current implementation — they fall back to `audit_log_key = "minio-unavailable"`. These metrics make failures visible.

### `modelguard_minio_write_errors_total`
- **Type:** Counter
- **Labels:** `bucket` (`modelguard-auditlog`, `modelguard-reports`, `modelguard-models`), `operation` (`put`, `get`, `list`)
- **Description:** Total failed MinIO operations. Any non-zero value warrants investigation.
- **OE Dashboard use:** Storage Health section; triggers a MinIO error alert.

### `modelguard_minio_write_duration_seconds`
- **Type:** Histogram
- **Labels:** `bucket`
- **Description:** Latency of MinIO `put_object` calls.
- **OE Dashboard use:** Detects MinIO slowdowns before they cause timeouts.

### `modelguard_registered_models_total`
- **Type:** Gauge
- **Labels:** none
- **Description:** Current count of registered models in `modelguard-models`. Polled on dashboard load.
- **Currently emitted:** Via `GET /stats` → `total_models` field.
- **OE Dashboard use:** Statistics page "Registered Models" metric.

---

## 3. Health / Subsystem Metrics

### `modelguard_subsystem_up`
- **Type:** Gauge (0 = down, 1 = up)
- **Labels:** `subsystem` (`api`, `frontend`, `minio`, `detector`)
- **Description:** Binary health of each subsystem as probed by `GET /health/detail`.
- **Currently emitted:** Via `GET /health/detail` JSON fields.
- **OE Dashboard use:** System Health page four-column metrics; sidebar Live System Health.

### `modelguard_detector_loaded`
- **Type:** Gauge (0 = not loaded, 1 = loaded)
- **Labels:** none
- **Description:** Whether the Isolation Forest model is trained and resident in memory.
- **Currently emitted:** `GET /health/detail` → `detector` field (`"loaded"` / `"not loaded"`).

---

## 4. Audit Log Metrics

These are derived by scanning MinIO object listings — they do not require a streaming pipeline.

### `modelguard_audit_log_objects_total`
- **Type:** Gauge
- **Labels:** `model_id`, `date`
- **Description:** Total audit log objects stored for a given model and date.
- **How to collect:** `GET /audit/{model_id}?date=YYYY-MM-DD` → count of returned keys.
- **OE Dashboard use:** Audit Logs page row count.

### `modelguard_attack_report_objects_total`
- **Type:** Gauge
- **Labels:** `model_id`
- **Description:** Total HIGH/CRITICAL attack reports stored for a model.
- **How to collect:** `GET /reports/{model_id}` → count of returned keys.
- **OE Dashboard use:** Attack Reports page count; security event alert.

---

## 5. Risk Score Distribution

### `modelguard_risk_score`
- **Type:** Histogram
- **Labels:** `model_id`, `endpoint`
- **Buckets:** `[10, 20, 30, 40, 50, 60, 70, 80, 90, 100]`
- **Description:** Distribution of `risk_score` values (0–100) across all scored queries.
- **OE Dashboard use:** Risk level reference chart on System Health page; trend analysis.

---

## 6. Current Emission vs. Required

| Metric | Currently emitted | How |
|---|---|---|
| `modelguard_subsystem_up` (api, minio, detector, frontend) | Yes | `GET /health/detail` |
| `modelguard_registered_models_total` | Yes | `GET /stats` |
| `modelguard_request_rate_1m` | Yes | embedded in each audit log JSON as `request_rate_1m` |
| `modelguard_audit_log_objects_total` | Yes (on demand) | `GET /audit/{model_id}` |
| `modelguard_attack_report_objects_total` | Yes (on demand) | `GET /reports/{model_id}` |
| `modelguard_requests_total` | **No** — needs Prometheus counter in `main.py` |
| `modelguard_anomalies_total` | **No** — needs Prometheus counter in `main.py` |
| `modelguard_request_duration_seconds` | **No** — needs middleware timing |
| `modelguard_minio_write_errors_total` | **No** — currently only logged, not counted |
| `modelguard_risk_score` (histogram) | **No** — needs Prometheus histogram in `main.py` |

### Recommended implementation path

1. Add `prometheus_fastapi_instrumentator` to `api/requirements.txt` — auto-instruments request count and latency with zero code changes.
2. Add manual `Counter` increments in `analyze_query` and `predict` for `modelguard_anomalies_total` and `modelguard_risk_score`.
3. Wrap MinIO calls in a try/except that increments `modelguard_minio_write_errors_total` before re-raising.
4. Expose `/metrics` endpoint (Prometheus scrape target).
5. Add a Prometheus + Grafana service to `docker-compose.yml` for persistent metric storage.
