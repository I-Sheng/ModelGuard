# Threat Model: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.2.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-04-26

---

## Top Threats

### T-01 — Model Artifact Overwrite via Upload Without Ownership Check (High)

`POST /models/{model_id}/upload` constructs the MinIO key as `{model_id}/artifacts/{file.filename}` and calls `put_object` unconditionally. There is no check that the caller owns or registered the target `model_id`, and no versioning or conflict guard. Any authenticated user can overwrite another model's existing artifact by supplying the victim's `model_id` and a matching filename, silently replacing the stored binary with arbitrary content — including a backdoored or deliberately degraded model.

**Component**: Backend API  
**STRIDE**: Tampering, Elevation of Privilege

---

### T-02 — Data Tampering: Attack Reports Derived from Mutable Audit Logs (High)

Attack reports stored in `modelguard-reports` are generated from audit log entries in `modelguard-auditlog`. MinIO object locking (WORM) is not enabled on either bucket. An attacker who obtains root MinIO credentials or a forged admin JWT can silently modify or delete audit log records before a report is produced, causing the derived report to reflect falsified history — suppressing evidence of an extraction campaign or injecting phantom alerts to mask real activity.

**Component**: MinIO storage, Backend API  
**STRIDE**: Tampering, Repudiation

---

### T-03 — DDoS Attack: No Rate Limit on Any Endpoint (Medium)

No rate-limiting middleware exists on any endpoint. An unauthenticated or authenticated attacker can flood any route — most critically `/predict` and `/token` — with high-volume requests. Against `/predict`, this exhausts MinIO write capacity and fills `modelguard-auditlog` until disk is exhausted; once writes fail the API silently continues without storing logs, creating a detection blind spot. Against `/token`, it enables credential-stuffing at full API throughput with no lockout. The lack of a `max_length` validator on `query_text` compounds the impact, since each request can carry arbitrarily large payloads.

**Component**: Backend API, MinIO storage  
**STRIDE**: Denial of Service
