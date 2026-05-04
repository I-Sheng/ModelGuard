You are a startup pitch deck writer. Create a 10-slide pitch presentation for ModelGuard AI, 
an open-source ML security tool. Use the following project details.

---

## Product

ModelGuard AI detects model theft attacks in real-time by analyzing API query patterns and 
behavioral anomalies, protecting enterprise ML models from IP extraction and poisoning.

It sits inline with a deployed ML model and scores every incoming query 0–100 (LOW / MEDIUM 
/ HIGH / CRITICAL) for signs of:
- Model extraction — systematic querying to reconstruct model weights
- Membership inference — probing for training data signals
- Anomalous request bursts — automated high-rate API sweeps

## Detection Engine

Isolation Forest trained on four behavioral features per query:
- query_length
- unique_token_ratio (low = repetitive probing pattern)
- Shannon entropy
- request_rate_1m (queries in last 60 seconds)

HIGH and CRITICAL events trigger a dedicated attack report stored durably in S3-compatible 
object storage.

## Architecture (5 services, Docker Compose)

- FastAPI backend: JWT auth + RBAC (ml_user / customer / admin roles), Isolation Forest 
  detector, MinIO audit writes
- SwaggerAI frontend: role-scoped OpenAPI spec — each user only sees their permitted endpoints
- Streamlit OE Dashboard: real-time health, audit logs, and attack reports for ops teams
- MinIO: S3-compatible durable storage for model artifacts, audit logs, and attack reports
- One-shot init container: bucket bootstrap

## Key Security Features

- JWT-based auth + RBAC on all endpoints
- Audit log on every single request
- Dedicated attack report stored for HIGH/CRITICAL events
- Role-scoped API surface (customers can't see admin endpoints)

## Known Limitations / Open Threats (honest risk register)

- T-01: No model artifact ownership check — any authenticated user can overwrite another's model
- T-02: Audit logs are mutable — MinIO WORM not yet enabled
- T-03: No rate limiting — DDoS / credential stuffing possible at full API throughput

## Roadmap

- Persistent per-client rate tracking (Redis/TimescaleDB replacing in-memory window)
- Webhook / Slack alerting on CRITICAL events
- Real model artifact checksum validation
- Fix T-01/T-02/T-03 mitigations

---

## Slide Structure

1. **Problem** — The $B enterprise ML IP theft problem; models cost millions to train and are 
   exposed via APIs
2. **Solution** — ModelGuard: real-time anomaly detection inline with your ML API
3. **How It Works** — Detection pipeline (feature extraction → Isolation Forest → risk score 
   → audit + report)
4. **Architecture** — Deployment topology diagram showing ModelGuard's position in the stack.

   The diagram should show left-to-right flow:

   [End User]
       ↓
   [Frontend / Client App]  ← faces the user
       ↓
   [ModelGuard]             ← sits here, inline between frontend and load balancer
       ↓  (every query scored, audited, and optionally blocked before it goes further)
   [Load Balancer]
       ↓
   [ML API Backend]  ← can be cloud-hosted (AWS SageMaker, GCP Vertex, Azure ML)
                        or on-premises (self-hosted inference server)

   Key callouts on the diagram:
   - ModelGuard intercepts 100% of traffic — zero query passes unscored
   - Audit log written to durable object storage on every request
   - HIGH/CRITICAL events trigger an attack report and can short-circuit the request 
     before it ever reaches the model
   - The ML backend is provider-agnostic — ModelGuard is not coupled to any cloud

   Speaker notes: "ModelGuard is a drop-in proxy layer. Your frontend and your model 
   don't change — you insert ModelGuard between them. It doesn't matter whether your 
   inference endpoint is SageMaker, a self-hosted GPU cluster, or a third-party API. 
   As long as queries flow through ModelGuard, every request is scored."

5. **Threat Coverage** — What attacks we catch and how (model extraction, membership inference, 
   burst anomalies)
6. **Security Model** — RBAC, role-scoped API, durable audit trail, attack reports
7. **Demo** — Live smoke test: register a model → send normal query → send extraction query → 
   view attack report in OE Dashboard
8. **Known Risks & Roadmap** — Honest T-01/T-02/T-03 register with mitigation timeline; shows 
   maturity
9. **Traction / Status** — v0.2.0-oss, open source, Docker Compose deployable, active security 
   test suite
10. **Ask** — [Fill in: funding ask, partnerships, pilot customers, etc.]

For each slide provide: a title, 3–5 bullet points of speaker notes, and a suggested visual 
or diagram. Keep language crisp and non-technical enough for a mixed technical/business audience.
