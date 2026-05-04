# Threat Model: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.3.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-05-03

---

## Top Threats

### T-01 — Batch Data Injection: Falsified Query Logs Bypass or Fabricate Theft Detection (High)

`POST /batch/analyze` accepts a JSON payload of query records (`query_id`, `query_user`, `input`, `output`) supplied entirely by the submitting partner. There is no cryptographic signature, hash chain, or out-of-band verification that the submitted records match the partner's actual production logs. A malicious or compromised partner can:

- **Suppress detection** — omit the queries of a user actively stealing their model from the batch before submission.
- **Fabricate alerts** — inject synthetic queries attributed to a competitor or target user to generate false HIGH/CRITICAL theft reports.

Because ModelGuard's detection output is only as trustworthy as the input batch, unverified batch integrity is the highest-impact single point of manipulation in the pipeline.

**Component**: Backend API  
**STRIDE**: Tampering, Spoofing, Repudiation

---

### T-02 — Data Tampering: Theft Reports Derived from Mutable Audit Logs (High)

Theft reports stored in `modelguard-reports` are generated from batch analysis records in `modelguard-auditlog`. MinIO object locking (WORM) is not enabled on either bucket. An attacker who obtains root MinIO credentials or a forged admin JWT can silently modify or delete audit records before a report is produced, causing the derived report to reflect falsified history — suppressing evidence of a theft campaign or injecting phantom alerts to mask real activity.

**Component**: MinIO storage, Backend API  
**STRIDE**: Tampering, Repudiation

---

### T-03 — DDoS Attack: No Rate Limit on Any Endpoint (Medium)

No rate-limiting middleware exists on any endpoint. An unauthenticated or authenticated attacker can flood any route — most critically `/batch/analyze` and `/auth/login` — with high-volume requests. Against `/batch/analyze`, this exhausts MinIO write capacity and fills `modelguard-auditlog` until disk is exhausted; once writes fail the API silently continues without storing records, creating a detection blind spot. Against `/auth/login`, it enables credential-stuffing at full API throughput with no lockout. The lack of a `max_records` validator on batch payloads compounds the impact, since each request can carry an arbitrarily large list of query records.

**Component**: Backend API, MinIO storage  
**STRIDE**: Denial of Service
