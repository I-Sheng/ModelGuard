# ModelGuard AI — Security Presentation

---

## Slide 1 — Why This Product?

AI models are expensive to build and easy to steal.

A motivated attacker only needs API access to systematically query a deployed model and rebuild a near-identical copy — no source code, no weights, no breach required. This is called model extraction, and most organisations have no visibility into when it is happening.

**ModelGuard sits in front of your model endpoint.** It scores every query in real time, flags suspicious patterns, and writes a tamper-evident audit trail — so you know if someone is mapping your model's decision boundary before they've finished.

---

## Slide 2 — Top 3 Risks

---

### Risk 1 — JWT Signing Secret Committed to the Public Repository *(Critical)*

**What:** The secret used to sign all authentication tokens is hardcoded as `"modelguard-dev-secret-change-in-production"` in `main.py` and committed to the public repo.

**Why it is #1:** Authentication is the entire security boundary between the public internet and admin-level operations (audit logs, model uploads, attack reports). A single line of source code lets an attacker forge a permanent admin token — no password, no brute-force, no exploit. Every other control collapses behind it.

---

### Risk 2 — Default MinIO Credentials Hardcoded in docker-compose.yml *(Critical)*

**What:** `minioadmin / minioadmin` is hardcoded for the MinIO storage service and repeated in the backend container environment. MinIO ports 9000 and 9001 are bound to `0.0.0.0`.

**Why it is #2:** MinIO holds the three things ModelGuard exists to protect — model artifacts, audit logs, and attack reports. With the default credentials, an attacker can read model weights, delete the entire audit trail to erase evidence of an extraction campaign, and access every attack report. There is no object locking, so deletion is silent and irreversible.

---

### Risk 3 — Model Artifact Overwrite via Upload Without Ownership Check *(High)*

**What:** `POST /models/{model_id}/upload` has no ownership validation. Any authenticated customer can upload a file targeting any `model_id` with any filename, silently replacing another customer's stored artifact.

**Why it is #3:** Model artifacts are the core IP ModelGuard is built to protect. A malicious customer can overwrite a competitor's binary with a backdoored or corrupted version — same filename, same model ID, no error returned. There is no versioning to recover from, and the audit trail only records that an upload occurred, not that it was unauthorized.
