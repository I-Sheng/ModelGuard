# ModelGuard AI — Presentation 2

---

## Slide 1 — What Changed Since Last Time

Since the first presentation we have made three structural improvements.

First, MinIO storage credentials are no longer hardcoded — `docker-compose.yml` now reads `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` from the environment, and the backend service has its own dedicated access key pair separate from the root admin account.

Second, we shipped a full CI/CD pipeline: GitHub Actions runs the security and functional test suite on every push, and a CD workflow publishes a signed container image to GHCR on merge to main.

Third, we added an OE (Operations Engineering) dashboard — a Streamlit app that gives the on-call team a live view of partner submission health, system status, and historical theft reports without needing direct MinIO or API access.

---

## Slide 2 — Top 3 Business Risks

---

### Risk 1 — Silent False Negatives *(Critical)*

**What:** If a real extraction campaign runs below the detection threshold the system reports nothing. The silence looks identical to a clean system.

**Why it is #1:** Stolen model IP is irreversible. A customer who chose ModelGuard expecting protection and received none has both a legal claim and a catastrophic business loss. There is currently no canary, no baseline detection test, and no cross-batch user-trend view — a low-and-slow campaign spread across multiple submission windows is completely invisible today.

---

### Risk 2 — No Per-Partner Risk Calibration *(High)*

**What:** Detection thresholds are hardcoded in the backend. There is no mechanism to tune sensitivity per customer, store those thresholds, or display them to an operator.

**Why it is #2:** Risk tolerance is not the same across customers. A financial services firm running a proprietary pricing model has near-zero tolerance for a missed extraction; a consumer API can accept more false positives in exchange for fewer false negatives. Selling both customers the same undifferentiated threshold makes ModelGuard uncompetitive and exposes it to churn the moment a customer compares notes with a peer.

---

### Risk 3 — Detector Accuracy Is Unverifiable in Production *(High)*

**What:** The OE dashboard confirms the detector is `LOADED`. It does not confirm it is producing calibrated or accurate scores. There are no performance metrics, no drift signal, and no scheduled canary injection.

**Why it is #3:** A degraded model looks healthy until after an extraction incident. Engineering accuracy goals are disconnected from the business goal of actually catching theft. An operator watching the dashboard today has no signal that tells them whether the model that was accurate at training time is still accurate on today's query distribution.

---

## Slide 3 — OE Dashboard Demo

OE dashboard demo

---

## Slide 4 — How We Resolved the Risks from Presentation 1

---

### Risk 1 Resolution — JWT Secret Moved to Environment Variable

The JWT signing secret is no longer a hardcoded string in source. `main.py` reads it from `JWT_SECRET_KEY` at startup:

```
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "modelguard-dev-secret-change-in-production")
```

The `.env` file (gitignored) is the authoritative source for production. The fallback default ensures local development still boots without manual setup and is clearly labelled for replacement.

---

### Risk 2 Resolution — MinIO Credentials Externalized

`docker-compose.yml` no longer contains any hardcoded `minioadmin` values. Both the MinIO service and the backend container read credentials from environment variables:

```
MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
```

The backend also uses a dedicated service account key pair created by `minio-init` at bootstrap, so the root admin credential is never passed to application code.

---

### Risk 3 — Model Artifact Overwrite (Open)

The ownership check on `POST /models/{model_id}/upload` has not yet been implemented. Any authenticated partner can still overwrite another partner's stored artifact by targeting their `model_id`. This remains an open item for the next sprint.
