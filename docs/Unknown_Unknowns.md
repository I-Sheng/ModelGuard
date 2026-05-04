# Unknown Unknowns: Potential Risks Not Yet Modeled

---

- Status: Living document — expand as unknowns are discovered
- Version: 0.2.0
- Last Updated: 2026-05-03

---

This document captures risk areas that are not yet understood well enough to be written up as concrete threats in the Threat Model. Each entry names the surface, explains why it is opaque, and identifies what investigation or instrumentation would be needed to resolve the uncertainty.

---

## U-01 — Upstream Dependency Supply Chain

**Surface**: `api/requirements.txt`, `oe-dashboard/requirements.txt`

**Why it is opaque**: All packages are pinned to a minor version but not to a hash. Any of these packages could receive a malicious point release or have an existing version silently tampered with on PyPI (see `python-jose` CVE history, `scikit-learn` build artifacts). Docker base images (`minio/minio:latest`, `minio/mc:latest`) are unpinned entirely — `latest` can be a different binary on every `docker compose pull`.

**What would resolve it**:
- Hash-pin all Python packages with `pip-compile --generate-hashes`
- Pin MinIO images to a specific digest (`image: minio/minio@sha256:...`)
- Enable Dependabot or equivalent to surface newly published CVEs
- Add a software bill of materials (SBOM) step to CI

---

## U-02 — Isolation Forest Detector Poisoning via Training Distribution Drift

**Surface**: `api/main.py` — `_TRAIN_DATA` synthetic samples, trained at startup; detector persisted to `modelguard-detectors` in MinIO

**Why it is opaque**: The detector is trained once on fixed synthetic rows representing normal user behavior. There is no monitoring of real-world feature distribution drift across submitted batches. If legitimate user behavior shifts (e.g., a new class of AI application produces high `query_count` users that are benign), the detector's anomaly boundary moves without any alert. An attacker who understands the training distribution could also craft queries that land just inside the boundary across many batch windows, avoiding detection indefinitely.

Additionally, the persisted detector file in MinIO (`modelguard-detectors/v1/detector.pkl`) could be replaced by an attacker with MinIO credentials, causing the backend to load a compromised model that suppresses all alerts or flags arbitrary users.

**What would resolve it**:
- Log per-user feature vectors for every batch and periodically compare to the training distribution (KL divergence or histogram comparison)
- Set a threshold at which a retraining alert is raised
- Hash-verify the detector file loaded from MinIO against a known-good checksum stored out-of-band
- Red-team the detector with adversarial batches designed to stay below the anomaly threshold

---

## U-03 — JWT Secret Strength and Rotation

**Surface**: `api/main.py` — `SECRET_KEY` env var, HS256 signing

**Why it is opaque**: The application reads `SECRET_KEY` from the environment at startup but there is no enforcement of minimum entropy, no rotation mechanism, and no revocation list. If the key leaks, all tokens signed with it are valid indefinitely until the service is restarted with a new key. The blast radius and detection time for such a leak are unknown.

**What would resolve it**:
- Enforce a minimum key length (>= 256 bits) at startup with a hard failure
- Document a key rotation runbook (how to rotate without downtime, how to invalidate existing sessions)
- Consider adding a token revocation check (short-lived tokens + refresh, or a deny-list in Redis/MinIO)

---

## U-04 — MinIO Credential Exposure via Container Environment

**Surface**: `docker-compose.yml` — `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_ACCESS_KEY` injected as env vars

**Why it is opaque**: Any process inside the container, any log line that dumps `os.environ`, or any `docker inspect` by a user with Docker socket access can expose the MinIO root credentials. The scope of who has Docker socket access on the host is unknown and is not enforced by this codebase.

**What would resolve it**:
- Audit who has Docker socket access on each deployment host
- Prefer Docker secrets or a secrets manager over plain env vars for MinIO root credentials
- Verify that no log statement in `main.py` or `app.py` can emit environment variable contents

---

## U-05 — CORS Policy and Cross-Origin Request Forgery

**Surface**: `api/main.py` — `CORSMiddleware` configuration

**Why it is opaque**: The exact `allow_origins` value is not visible without reading the running config. If it is set to `["*"]` (common during development) it allows any origin to make credentialed cross-origin requests to the API. Combined with JWT tokens stored in `localStorage` (the typical Swagger UI pattern), this creates a CSRF/XSS pivot path whose impact depends on who is logged in.

**What would resolve it**:
- Confirm `allow_origins` is locked to the known frontend origin in all non-development environments
- Confirm tokens are not stored in `localStorage` in production deployments
- Add a CORS misconfiguration check to the security test suite

---

## U-06 — Batch Payload Size and Content Validation

**Surface**: `POST /batch/analyze` — `queries` list in the JSON body

**Why it is opaque**: The endpoint accepts an arbitrarily long list of query records with no enforced upper bound on the number of records, the length of individual `input` or `output` strings, or the character set. A single oversized batch (e.g., 1 million records with 10KB inputs) could exhaust backend memory or CPU during feature computation. Additionally, there is no validation that `query_id` values are unique within a batch, which could skew per-user aggregation silently.

**What would resolve it**:
- Enforce a maximum `len(queries)` per batch request (e.g., 100,000)
- Enforce a maximum string length on `input` and `output` fields
- Validate that `query_id` values are unique within the batch
- Add a payload size check to the security test suite

---

## U-07 — Partner Identity Verification

**Surface**: `POST /batch/analyze` — `partner_id` field in the request body

**Why it is opaque**: The `partner_id` field in the batch payload is caller-supplied and is not verified against the authenticated JWT's identity. A partner authenticated as `partner-A` could submit a batch claiming `partner_id = partner-B`, causing the audit log and report to be filed under a different partner's namespace. This could be used to pollute another partner's audit history or to avoid attribution of a suspicious batch.

**What would resolve it**:
- Derive `partner_id` from the authenticated JWT's `username` (or a `partner_id` claim), not from the request body
- Add a test that confirms a partner cannot submit batches under a different `partner_id`

---

## U-08 — Streamlit Dashboard Authentication and Session Isolation

**Surface**: `oe-dashboard/app.py` — admin JWT obtained at startup, shared across all dashboard sessions

**Why it is opaque**: The dashboard obtains a single admin JWT at process startup and uses it for all backend calls regardless of which browser session is active. If the Streamlit port (8501) is accessible to anyone on the network (or the internet), every visitor effectively has admin-level read access to all partner audit logs and theft reports without authenticating. The exposure window and network topology are not documented.

**What would resolve it**:
- Confirm that port 8501 is not publicly reachable without additional network controls (firewall, VPN, reverse proxy with auth)
- Consider requiring per-session login in the dashboard rather than a shared startup credential
- Add this surface to the threat model if it is reachable from outside the operator's trusted network

---

## How to Promote an Unknown to the Threat Model

When an item here is investigated and the risk is well-understood, move it to `Threat_Model.md` as a numbered threat (T-0N) with STRIDE classification and severity, and remove it from this document. If investigation shows no risk, close it with a one-line note and the date.
