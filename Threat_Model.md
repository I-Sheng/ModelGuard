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
**Mitigation**: Record the registering user on `POST /models/register`; verify on upload that the caller's JWT `username` matches the registered owner (or is `admin`); enable MinIO object versioning on `modelguard-models` so overwrites are recoverable and auditable.

---

### T-02 — Data Tampering: Attack Reports Derived from Mutable Audit Logs (High)

Attack reports stored in `modelguard-reports` are generated from audit log entries in `modelguard-auditlog`. MinIO object locking (WORM) is not enabled on either bucket. An attacker who obtains root MinIO credentials or a forged admin JWT can silently modify or delete audit log records before a report is produced, causing the derived report to reflect falsified history — suppressing evidence of an extraction campaign or injecting phantom alerts to mask real activity.

**Component**: MinIO storage, Backend API  
**STRIDE**: Tampering, Repudiation  
**Mitigation**: Enable MinIO object locking with a WORM retention policy on `modelguard-auditlog` and `modelguard-reports`; validate report generation against a content-hash of the source audit entries; ship logs to an out-of-band append-only sink independent of the MinIO instance.

---

### T-03 — DDoS Attack: No Rate Limit on Any Endpoint (Medium)

No rate-limiting middleware exists on any endpoint. An unauthenticated or authenticated attacker can flood any route — most critically `/predict` and `/token` — with high-volume requests. Against `/predict`, this exhausts MinIO write capacity and fills `modelguard-auditlog` until disk is exhausted; once writes fail the API silently continues without storing logs, creating a detection blind spot. Against `/token`, it enables credential-stuffing at full API throughput with no lockout. The lack of a `max_length` validator on `query_text` compounds the impact, since each request can carry arbitrarily large payloads.

**Component**: Backend API, MinIO storage  
**STRIDE**: Denial of Service  
**Mitigation**: Add `slowapi` rate-limiting middleware (e.g. 60 req/min per IP on `/predict`, 10 req/min on `/token`); add `max_length=10_000` to the `query_text` Pydantic field; configure MinIO bucket size quotas; place an API gateway or reverse proxy in front of the service.
