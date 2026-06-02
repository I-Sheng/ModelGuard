# Threat Model: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.3.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-06-02

---

## Top Threats

### T-01 — Batch Data Injection: Falsified Query Logs Bypass or Fabricate Theft Detection (High)

`POST /batch/analyze` accepts a JSON payload of query records (`query_id`, `query_user`, `input`, `output`) supplied entirely by the submitting partner. There is no cryptographic signature, hash chain, or out-of-band verification that the submitted records match the partner's actual production logs. A malicious or compromised partner can:

- **Suppress detection** — omit the queries of a user actively stealing their model from the batch before submission.
- **Fabricate alerts** — inject synthetic queries attributed to a competitor or target user to generate false HIGH/CRITICAL theft reports.

Because ModelGuard's detection output is only as trustworthy as the input batch, unverified batch integrity is the highest-impact single point of manipulation in the pipeline.

**Component**: Backend API  
**STRIDE**: Tampering, Spoofing, Repudiation

**Mitigation (implemented)**: `POST /batch/analyze` now requires an HMAC-SHA256 signature over the raw request body, verified server-side against `BATCH_HMAC_SECRET`. Requests with a missing or invalid `X-Batch-Signature` header are rejected with HTTP 403. Signature failures are logged to an in-memory audit list accessible at `GET /admin/hmac-failures`. Operators can suspend a misbehaving API user via `POST /admin/users/{username}/suspend` and reverse it with `DELETE /admin/users/{username}/suspend`. See `docs/T01_HMAC_Integrity_Runbook.md` for the full response procedure.

---

### T-02 — Data Tampering: Theft Reports Derived from Mutable Audit Logs (High)

Theft reports stored in `modelguard-reports` are generated from batch analysis records in `modelguard-auditlog`. MinIO object locking (WORM) is not enabled on either bucket. An attacker who obtains root MinIO credentials or a forged admin JWT can silently modify or delete audit records before a report is produced, causing the derived report to reflect falsified history — suppressing evidence of a theft campaign or injecting phantom alerts to mask real activity.

**Component**: MinIO storage, Backend API  
**STRIDE**: Tampering, Repudiation

**Mitigation (implemented)**: Both `modelguard-auditlog` and `modelguard-reports` buckets are now provisioned with MinIO object locking (`mc mb --with-lock`). Objects written to these buckets cannot be modified or deleted once stored, making the audit trail append-only.

---

### T-03 — DDoS Attack: No Rate Limit on Any Endpoint (Medium)

No rate-limiting middleware exists on any endpoint. An unauthenticated or authenticated attacker can flood any route — most critically `/batch/analyze` and `/auth/login` — with high-volume requests. Against `/batch/analyze`, this exhausts MinIO write capacity and fills `modelguard-auditlog` until disk is exhausted; once writes fail the API silently continues without storing records, creating a detection blind spot. Against `/auth/login`, it enables credential-stuffing at full API throughput with no lockout. The lack of a `max_records` validator on batch payloads compounds the impact, since each request can carry an arbitrarily large list of query records.

**Component**: Backend API, MinIO storage  
**STRIDE**: Denial of Service

**Mitigation (implemented)**: `slowapi` rate-limiting middleware is now applied at the route level. `/auth/login` is capped at 10 requests/minute per IP to prevent credential stuffing. `/batch/analyze` is capped at 60 requests/minute per IP to bound MinIO write volume. Requests exceeding either limit receive HTTP 429.
