# Threat Model: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.2.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-04-20

---

## Top Threats

### T-01 — JWT Signing Secret Committed to Public Repository (Critical)

The `JWT_SECRET_KEY` defaults to `"modelguard-dev-secret-change-in-production"` and is committed in plain text to the public repository (`main.py`). Any attacker who reads the source can forge a valid `admin` JWT with an arbitrary expiry, bypassing the entire authentication layer without needing credentials.

**Component**: Backend API  
**STRIDE**: Spoofing  
**Mitigation**: Generate a random secret (≥32 bytes) at deploy time; inject via environment variable or secret manager; remove the hardcoded default.

---

### T-02 — Hardcoded User Credentials in Source Code (Critical)

The `_USERS` dictionary in `main.py` contains plaintext passwords (`admin_password`, `customer_password`, `ml_password`) committed to the public repository. All three accounts — including the admin — are fully disclosed to any repository reader.

**Component**: Backend API  
**STRIDE**: Spoofing  
**Mitigation**: Remove passwords from source; load from environment variables or a secret manager at startup; rotate all defaults before any shared deployment.

---

### T-03 — Default MinIO Credentials Hardcoded in docker-compose.yml (Critical)

`MINIO_ROOT_USER: minioadmin` / `MINIO_ROOT_PASSWORD: minioadmin` are hardcoded in `docker-compose.yml` and repeated in the `backend` environment block. Any host with network access to port 9000 or 9001 can authenticate to MinIO and read, overwrite, or delete all three buckets (models, audit logs, attack reports).

**Component**: MinIO storage  
**STRIDE**: Spoofing, Elevation of Privilege  
**Mitigation**: Inject MinIO credentials via a `.env` file excluded from git; never use `minioadmin` outside local development; bind ports 9000/9001 to `127.0.0.1`.

---

### T-04 — Model Artifact Overwrite via Upload Without Ownership Check (High)

`POST /models/{model_id}/upload` constructs the MinIO key as `{model_id}/artifacts/{file.filename}` and calls `put_object` unconditionally. There is no check that the caller owns or registered the target `model_id`, and no versioning or conflict guard. Any authenticated `customer` can overwrite another model's existing artifact by uploading a file with the same `model_id` and filename, silently replacing the stored binary with arbitrary content.

**Component**: Backend API  
**STRIDE**: Tampering  
**Mitigation**: Record the registering user on `POST /models/register`; verify on upload that the caller's JWT `username` matches the registered owner (or is `admin`); alternatively, enable MinIO object versioning on `modelguard-models` so overwrites are recoverable.

---

### T-05 — Path Traversal via Unsanitized Filename in Artifact Upload (High)

`POST /models/{model_id}/upload` constructs the MinIO key as `{model_id}/artifacts/{file.filename}` with no sanitization. A crafted filename such as `../metadata.json` resolves to `{model_id}/metadata.json`, allowing an authenticated `customer` to overwrite the model's own registered metadata or any other object in the same bucket prefix.

**Component**: Backend API  
**STRIDE**: Tampering  
**Mitigation**: Normalize `file.filename`; strip path separators; restrict to safe characters (`[a-zA-Z0-9._-]`) and enforce a maximum length before constructing any storage key.

---

### T-06 — Feature Evasion via Public Training Distribution (High)

The Isolation Forest is trained on a synthetic normal distribution whose parameters (`loc=[120, 0.6, 3.5, 2.0]`, `scale=[40, 0.1, 0.5, 0.8]`) are hardcoded and publicly visible in `main.py`. The 4-feature vector definition is equally public. A model thief can read the source, craft queries that sit within the normal region (short text, varied tokens, moderate entropy, low rate), and conduct a slow extraction campaign that never triggers HIGH/CRITICAL alerts.

**Component**: Isolation Forest detector  
**STRIDE**: Tampering (evasion)  
**Mitigation**: Add temporal features (per-client daily query counts, sliding-window budget); expand the feature vector with semantic signals; do not rely solely on per-request scoring.

---

### T-07 — Audit Log Deletion with No Object Lock (High)

MinIO object locking (WORM) is not enabled on `modelguard-auditlog` or `modelguard-reports`. An attacker who obtains the root MinIO credentials (see T-03) or a forged admin JWT (see T-01) can delete all audit records, destroying the forensic trail and erasing evidence of a prior extraction campaign.

**Component**: MinIO storage  
**STRIDE**: Tampering, Repudiation  
**Mitigation**: Enable MinIO object locking with a retention policy on both audit buckets; ship logs to an out-of-band append-only sink independent of the MinIO instance.

---

### T-08 — No Rate Limiting or Query Size Cap Enables Storage Exhaustion DoS (Medium)

No rate-limiting middleware exists on any endpoint, and `query_text` has no `max_length` validator. An attacker with a valid JWT (or a forged one from T-01) can flood `/predict` with large payloads, filling `modelguard-auditlog` until the host disk is exhausted. Once MinIO writes fail, the API silently sets `audit_log_key = "minio-unavailable"` and continues — detection still runs but nothing is stored, creating an undetected blind spot.

**Component**: Backend API, MinIO storage  
**STRIDE**: Denial of Service  
**Mitigation**: Add `slowapi` rate-limiting middleware; add `max_length=10_000` to the `query_text` Pydantic field; configure MinIO bucket size quotas.
