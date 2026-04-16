# Threat Model: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.2.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-04-15

---

## 1. Scope and Objectives

This document covers the threat surface of the ModelGuard AI stack as deployed via Docker Compose: the FastAPI backend, SwaggerAI frontend, OE Dashboard, and MinIO object storage. It identifies assets worth protecting, trust boundaries, threat actors, concrete attack scenarios (using STRIDE), and the current mitigation status of each.

**What is in scope:**
- The Backend API (port 8000) and all its endpoints
- MinIO storage and the three buckets it hosts
- The Isolation Forest detection engine
- The SwaggerAI frontend (port 3000, nginx)
- The OE Dashboard (port 8501, Streamlit)
- Docker Compose network configuration

**What is out of scope:**
- The upstream ML model being protected (ModelGuard wraps it; the model itself is a separate system)
- Host OS and container runtime security
- Network perimeter controls (firewalls, VPNs)

---

## 2. Assets

| Asset | Description | Impact if Compromised |
|---|---|---|
| Model artifacts | Binary weights + metadata stored in `modelguard-models` | IP theft; the thing ModelGuard exists to prevent |
| Audit logs | Immutable query records in `modelguard-auditlog` | Loss of forensic trail; attacker covers tracks |
| Attack reports | HIGH/CRITICAL event records in `modelguard-reports` | Loss of incident history; blind to past breaches |
| Detection engine | Isolation Forest trained on startup | Evasion becomes trivial once model is characterised |
| MinIO credentials | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` in environment | Full read/write/delete access to all three buckets |
| Query content | Raw query text (truncated to 500 chars) in audit records | Privacy violation if queries contain PII or trade secrets |
| API availability | Ability to score queries in real time | Detection gap during downtime; legitimate traffic blocked |

---

## 3. Trust Boundaries

```
[ External Users / Clients ]
           │
           │  HTTP (port 3000)        ← Trust boundary 1: no auth (SwaggerAI nginx)
           ▼
  ┌──────────────────────┐
  │  SwaggerAI Frontend  │─────► Backend API (Docker internal)
  │  (modelguard-frontend│
  └──────────────────────┘

[ Operator / Internal Users ]
           │
           │  HTTP (port 8501)        ← Trust boundary 2: no auth (OE Dashboard)
           ▼
  ┌──────────────────────┐
  │   OE Dashboard       │─────► Backend API (Docker internal)
  │ (modelguard-oe-dash) │
  └──────────────────────┘

           │  HTTP (port 8000)        ← Trust boundary 3: direct access (no auth)
           ▼
  ┌──────────────────────┐
  │   Backend API        │
  │ (modelguard-backend) │
  └────────┬─────────────┘
           │  S3 API (Docker internal network)
           │                          ← Trust boundary 4: shared static credentials
           ▼
  ┌──────────────────────┐
  │      MinIO           │
  │ (modelguard-minio)   │◄─── HTTP (port 9001) ← Trust boundary 5: console exposed
  └──────────────────────┘
```

**Key observation**: All five trust boundaries currently lack authentication. Any process that can reach port 3000, 8000, or 8501 has full access to all API operations. Any process that can reach port 9000/9001 with the default credentials has full storage access.

---

## 4. Threat Actors

| Actor | Goal | Capability |
|---|---|---|
| **Model thief** | Extract a functional replica of the protected model by querying it systematically | Automated tooling; large query budget; knowledge of ML extraction techniques |
| **Evasion attacker** | Submit extraction queries that ModelGuard does not flag | Knowledge of anomaly detection principles; ability to craft adversarial feature vectors |
| **Infrastructure attacker** | Compromise ModelGuard itself to delete audit logs, steal stored artifacts, or disable detection | Network access to exposed ports; credential brute-forcing |
| **Malicious insider** | Exfiltrate model artifacts or suppress attack reports | Direct access to the deployment environment |
| **Denial-of-service actor** | Exhaust API resources or MinIO storage to create a detection gap | High-volume request capability |

---

## 5. STRIDE Analysis

### 5.1 FastAPI Backend

| Threat | Description | Current State | Severity |
|---|---|---|---|
| **S**poofing | `client_id` is caller-supplied and unverified. An attacker can impersonate any client to poison per-client rate tracking. | No mitigation | Medium |
| **T**ampering | Request bodies are not signed. A man-in-the-middle on an HTTP (not HTTPS) deployment can alter query text before it reaches the detector. | No TLS in MVP | Medium |
| **R**epudiation | No authentication means any query can be denied by the caller. Audit logs record only what the caller claims their `client_id` is. | No mitigation | Medium |
| **I**nformation Disclosure | Query text (up to 500 chars) is written to MinIO. If queries contain PII or confidential data, storage becomes a liability. | Truncation to 500 chars only | Medium |
| **D**enial of Service | No rate limiting on any endpoint. An attacker can flood `/predict` to exhaust the in-memory `_query_window` list and skew rate-feature calculations for other clients. | No mitigation | High |
| **E**levation of Privilege | No RBAC. Any caller can register models (`POST /models/register`), upload artifacts (`POST /models/{id}/upload`), or overwrite existing metadata. | No mitigation | High |

### 5.2 MinIO Storage

| Threat | Description | Current State | Severity |
|---|---|---|---|
| **S**poofing | Default credentials (`minioadmin` / `minioadmin`) are shipped in the repository and in `docker-compose.yml`. Anyone with network access can authenticate. | Default creds hardcoded | Critical |
| **T**ampering | Anyone with MinIO credentials can overwrite or delete audit logs, destroying the forensic trail. MinIO versioning and object locking are not enabled. | No object lock | High |
| **R**epudiation | MinIO server-side access logs are not enabled by default. There is no record of who read or deleted an object. | No audit on storage layer | Medium |
| **I**nformation Disclosure | MinIO S3 API (port 9000) and console (port 9001) are bound to `0.0.0.0`. In a cloud deployment this exposes buckets to the public internet. | Ports open by default | Critical |
| **D**enial of Service | Storage exhaustion: an attacker with API access can flood `/predict` to fill `modelguard-auditlog` until the host disk is full, making new writes fail silently. | No storage quota | Medium |
| **E**levation of Privilege | The API container has full read/write/delete permissions to all buckets using the root MinIO credential. A compromised API process can delete all evidence. | Root credential in use | High |

### 5.3 Isolation Forest Detector

| Threat | Description | Current State | Severity |
|---|---|---|---|
| **T**ampering (evasion) | The feature vector is only 4 dimensions and the training distribution is public (hardcoded in `main.py`). An attacker who reads the source can craft queries that fall within the normal region: short text, high unique-token ratio, moderate entropy, low rate. | Feature spec is public | High |
| **T**ampering (rate evasion) | The request rate window (`_query_window`) is process-global, not per-client. An attacker using multiple `client_id` values (or no `client_id`) cannot be distinguished from many legitimate users. | No per-client rate tracking | High |
| **I**nformation Disclosure | The `decision_function` raw score is not returned in the API response, but the `risk_score` (a linear transform of it) is. An attacker can use binary search over query variants to characterise the decision boundary. | Risk score exposed | Medium |
| **D**enial of Service | The detector is loaded once at startup. If it raises an exception during `.predict()`, the entire request fails. No fallback scoring path exists. | No fallback | Low |

### 5.4 SwaggerAI Frontend (nginx, port 3000)

| Threat | Description | Current State | Severity |
|---|---|---|---|
| **S**poofing | No authentication on port 3000. Any user who can reach it can submit queries, register models, and upload artifacts. | No auth | High |
| **T**ampering | nginx proxies requests to the backend at `/api/*`. A misconfigured proxy rule could expose internal backend paths or allow SSRF. | Proxy config is minimal | Low |
| **I**nformation Disclosure | Swagger UI renders all response bodies including `query_text` snippets returned in error responses. PII in queries is visible in the browser. | No masking | Medium |

### 5.5 OE Dashboard (Streamlit, port 8501)

| Threat | Description | Current State | Severity |
|---|---|---|---|
| **S**poofing | No authentication on port 8501. Anyone who can reach it sees all audit logs and attack reports. | No auth | High |
| **I**nformation Disclosure | Attack report detail view renders the full stored JSON, which includes raw query text. If queries contain PII, it is displayed in the browser. | No masking in UI | Medium |
| **D**enial of Service | The "Fetch Audit Logs" button issues an unbounded `list_objects` call. A bucket with millions of entries will hang the dashboard. | No pagination | Low |

---

## 6. Attack Scenarios

### Scenario A — Evasion via Feature Stuffing

**Actor**: Model thief  
**Goal**: Extract model decision boundary without triggering HIGH/CRITICAL alerts

**Steps**:
1. Read `main.py` (open source) to identify the 4-feature vector and training distribution.
2. Craft extraction queries that are short (~100 chars), use varied tokens (high unique ratio), and are sent slowly (<3 req/min).
3. Each query returns the full prediction scores from `/predict`. Over thousands of slow queries the attacker builds a surrogate model.

**Why it works**: The Isolation Forest scores each query independently. A slow, low-volume extraction campaign with carefully shaped queries stays within the normal training distribution.

**Current gap**: No per-client session tracking, no cumulative anomaly budget, no velocity check across days.

---

### Scenario B — Audit Log Deletion

**Actor**: Infrastructure attacker or malicious insider  
**Goal**: Erase evidence of a past extraction campaign

**Steps**:
1. Obtain MinIO credentials (default: `minioadmin` / `minioadmin`, or read from environment via a compromised container).
2. Connect to MinIO S3 API on port 9000.
3. Delete all objects under `modelguard-auditlog/{model_id}/`.

**Why it works**: No object locking, no versioning, root credentials have delete permission, and no out-of-band backup exists.

**Current gap**: MinIO object lock (WORM) is not enabled. Storage-layer audit logging is off.

---

### Scenario C — Unauthenticated Model Registration

**Actor**: Any external caller with network access to port 8000  
**Goal**: Register a rogue model to pollute the model inventory or overwrite existing metadata

**Steps**:
1. `POST /models/register` with an arbitrary `model_id` (e.g., `sentiment-v1`) and malicious metadata.
2. The legitimate metadata is silently overwritten in `modelguard-models`.

**Why it works**: No API authentication and no write-access controls on model registration.

**Current gap**: No authentication layer, no ownership validation on model IDs.

---

### Scenario D — Storage Exhaustion DoS

**Actor**: DoS actor  
**Goal**: Disable detection by filling MinIO disk, causing all audit writes to fail silently

**Steps**:
1. Flood `POST /predict` at high rate with large query texts.
2. Each request writes a ~1 KB JSON object to `modelguard-auditlog`.
3. At 1000 req/s, disk fills at ~1 GB/s.
4. Once MinIO disk is full, `store_audit_log` raises an exception. The API catches it, sets `log_key = "minio-unavailable"`, and continues — detection still runs but nothing is stored.

**Why it works**: No rate limiting, no storage quota, and the MinIO write failure is silently swallowed.

**Current gap**: No request rate limiting middleware, no MinIO bucket size quota.

---

## 7. Risk Register

| ID | Threat | Likelihood | Impact | Risk | Status |
|---|---|---|---|---|---|
| T-01 | Default MinIO credentials exposed | High | Critical | **Critical** | Open |
| T-02 | No API authentication | High | High | **Critical** | Open |
| T-03 | Evasion via feature-aware query crafting | Medium | High | **High** | Open |
| T-04 | Audit log deletion (no object lock) | Medium | High | **High** | Open |
| T-05 | SwaggerAI frontend unauthenticated | High | High | **High** | Open |
| T-05b | OE Dashboard unauthenticated | High | Medium | **High** | Open |
| T-06 | Storage exhaustion DoS | Medium | Medium | **Medium** | Open |
| T-07 | Per-client rate evasion | High | Medium | **Medium** | Open |
| T-08 | PII in stored query text | Medium | Medium | **Medium** | Open |
| T-09 | Risk score oracle (binary search evasion) | Low | Medium | **Low** | Open |
| T-10 | MinIO ports bound to 0.0.0.0 | High | Low (internal) | **Low** | Open |

---

## 8. Mitigations

### Immediate (before any production exposure)

| ID | Threat(s) | Mitigation |
|---|---|---|
| M-01 | T-01 | Rotate MinIO credentials; inject via `.env` file excluded from git; never use `minioadmin` in any non-local environment |
| M-02 | T-02 | Add API key middleware to FastAPI (static key via `X-API-Key` header as a minimum; JWT for multi-tenant) |
| M-03 | T-10 | Bind MinIO ports to `127.0.0.1` in `docker-compose.yml`; expose only the API port externally |
| M-04 | T-05, T-05b | Add authentication to both frontends: API key header for SwaggerAI requests; Streamlit reverse-proxy basic auth or `st.experimental_user` for OE Dashboard |

### Short-term

| ID | Threat(s) | Mitigation |
|---|---|---|
| M-05 | T-04 | Enable MinIO object locking (WORM) on `modelguard-auditlog` and `modelguard-reports` buckets; set a retention policy |
| M-06 | T-06 | Add FastAPI rate-limiting middleware (e.g., `slowapi`); set per-IP and global request caps; configure MinIO bucket size quotas |
| M-07 | T-07 | Move `_query_window` to a per-client dictionary keyed by verified `client_id`; track cumulative daily query counts |
| M-08 | T-08 | Hash or redact query text before storage; store only feature vector and metadata in audit logs |

### Medium-term

| ID | Threat(s) | Mitigation |
|---|---|---|
| M-09 | T-03 | Add temporal features (queries-per-hour, queries-per-day per client); use a sliding-window anomaly budget rather than per-request scoring only |
| M-10 | T-03 | Expand feature vector with semantic features (TF-IDF similarity to known attack templates, n-gram patterns) to raise the cost of evasion |
| M-11 | T-09 | Add random noise (±2 points) to returned `risk_score` to degrade oracle utility without affecting operational thresholds |
| M-12 | T-04 | Ship audit logs to an out-of-band append-only sink (syslog, S3 with MFA-delete) independent of the MinIO instance that can be tampered |

---

## 9. Security Assumptions (MVP)

The following assumptions bound the current threat model. Violations would invalidate the risk ratings above.

1. **Deployment is internal only.** Ports 3000, 8000, 8501, 9000, and 9001 are not reachable from the public internet.
2. **The Docker host is trusted.** Host-level compromise is out of scope.
3. **Source code is public.** The feature vector, training distribution, and detection logic are known to any attacker who reads the repository.
4. **Queries are not legally sensitive.** No PII, health, or financial data is expected in `query_text` at MVP stage.
