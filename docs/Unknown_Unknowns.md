# Unknown Unknowns: Potential Risks Not Yet Modeled

---

- Status: Living document — expand as unknowns are discovered
- Version: 0.1.0
- Last Updated: 2026-04-26

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

## U-02 — Isolation Forest Model Poisoning via Training Data Drift

**Surface**: `api/main.py` — `_TRAIN_DATA` synthetic samples, trained at startup

**Why it is opaque**: The detector is trained once on 500 fixed synthetic rows at process startup. There is no monitoring of feature distribution drift over real traffic. If the real-world query distribution shifts significantly (e.g., a new legitimate model type with long queries and high entropy), the detector's anomaly boundary moves without any alert. An attacker who understands the training distribution could craft queries that land just inside the boundary indefinitely.

**What would resolve it**:
- Log feature vectors for every request and periodically compare to training distribution (KL divergence or a simple histogram)
- Set a threshold at which the model is retrained or an alert is raised
- Red-team the detector with adversarial inputs designed to stay below the anomaly threshold

---

## U-03 — JWT Secret Strength and Rotation

**Surface**: `api/main.py` — `SECRET_KEY` env var, HS256 signing

**Why it is opaque**: The application reads `SECRET_KEY` from the environment at startup but there is no enforcement of minimum entropy, no rotation mechanism, and no revocation list. If the key leaks (e.g., via a secrets manager misconfiguration or a logged environment dump), all tokens signed with it are valid indefinitely until the service is restarted with a new key. The blast radius and detection time for such a leak are unknown.

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

## U-06 — File Upload Content Validation

**Surface**: `POST /models/{model_id}/upload` — `UploadFile` stored to MinIO

**Why it is opaque**: The upload endpoint stores whatever bytes the client sends under a caller-controlled filename, with no MIME type check, no file size limit, no antivirus scan, and no validation that the file is a legitimate model artifact. A malicious pickle or ONNX file uploaded here could be deserialized by a downstream consumer and execute arbitrary code. The set of downstream consumers and their deserialization behavior is currently unknown.

**What would resolve it**:
- Define an allowlist of permitted file extensions and MIME types
- Enforce a maximum upload size
- Document all known consumers of model artifacts and whether they deserialize with `pickle`, `torch.load`, or a safer format
- Consider a sandbox deserialization check on ingest

---

## U-07 — process-global `_query_window` Under Concurrent Load

**Surface**: `api/main.py` — `_query_window: list[float]` used for per-request rate feature

**Why it is opaque**: `_query_window` is a module-level list mutated by every request handler. Under `uvicorn` with multiple workers (`--workers N`), each worker process has its own copy, so the rate estimate is per-worker, not per-service. Under a single worker with async concurrency, list append and list comprehension filtering are not atomic. The actual statistical behavior of the rate feature under real concurrency — and whether it can be gamed — has not been analyzed.

**What would resolve it**:
- Profile `_query_window` under concurrent load (e.g., with `locust`) and confirm the rate feature behaves as expected
- If multiple workers are ever used, move rate state to a shared store (Redis, or a single sidecar process)
- Add a note in the architecture doc about the single-worker assumption

---

## U-08 — Streamlit Dashboard Authentication and Session Isolation

**Surface**: `oe-dashboard/app.py` — admin JWT obtained at startup, shared across all dashboard sessions

**Why it is opaque**: The dashboard obtains a single admin JWT at process startup and uses it for all backend calls regardless of which browser session is active. If the Streamlit port (8501) is accessible to anyone on the network (or the internet), every visitor effectively has admin-level read access to audit logs and attack reports without authenticating. The exposure window and network topology are not documented.

**What would resolve it**:
- Confirm that port 8501 is not publicly reachable without additional network controls (firewall, VPN, reverse proxy with auth)
- Consider requiring per-session login in the dashboard rather than a shared startup credential
- Add this surface to the threat model if it is reachable from outside the operator's trusted network

---

## How to Promote an Unknown to the Threat Model

When an item here is investigated and the risk is well-understood, move it to `Threat_Model.md` as a numbered threat (T-0N) with STRIDE classification and severity, and remove it from this document. If investigation shows no risk, close it with a one-line note and the date.
