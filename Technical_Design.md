# **Technical Design Document: ModelGuard AI**

---

- Status: Initial Architecture / Baseline Release
- Version: 0.1.0-oss
- Repository: I-Sheng/ModelGuard

---

## **Overview**

**ModelGuard AI** is a real-time detection system for AI model theft attacks. It analyzes incoming API queries against deployed ML models to identify extraction attempts (membership inference, query-based stealing) and data poisoning through behavioral anomaly detection. The system provides risk scores, attack signatures, and automated alerts for enterprise ML teams.

**Core value proposition**: Protects high-value proprietary models (LLMs, vision systems, recommendation engines) from IP theft costing companies $50M+ annually in lost R&D.

## **Motivation**

- **AI model theft exploding**: 2026 sees 300% increase in model extraction attacks as enterprises deploy custom LLMs
- **Current tools fail**: Traditional WAFs miss model-specific patterns; manual monitoring unscalable
- **Expertise fit**: Leverages my ML TA experience, LLM knowledge, and security expertise
- **Market timing**: AI security startups raised $1.2B in Q1 2026; agentic detection is the next wave

## **Project Components & Requirements**

## **MVP Scope (4 weeks)**

```c
Core Components:
├── API Query Monitor (Python/FastAPI)
│   ├── Query parser & feature extractor
│   ├── Anomaly detector (Isolation Forest + rules)
│   └── Risk scoring engine
├── Streamlit Dashboard
│   ├── Real-time risk dashboard
│   ├── Model inventory & attack history
│   └── Alert configuration
├── Alerting (Email/Slack)
└── SQLite persistence (MVP)
```

## **Functional Requirements**

1. **Real-time analysis**: <100ms latency per query
2. **Detection accuracy**: >92% true positive rate on synthetic theft dataset
3. **Risk scoring**: 0-100 score with confidence intervals
4. **Dashboard**: Model list, live risk feed, historical attacks
5. **Alerts**: Configurable thresholds (email/Slack)

## **Non-Functional Requirements**

- **Scalability**: 1000 queries/second (horizontal scaling via Docker)
- **Availability**: 99.9% uptime with health checks
- **Security**: API key auth, rate limiting, audit logging
- **Observability**: Structured logs, metrics dashboard

## **Out of Scope (MVP)**

- ❌ Agentic auto-mitigation (block/quarantine)
- ❌ Multi-tenant support
- ❌ Advanced ML (transformer-based detectors)
- ❌ Kubernetes deployment
- ❌ Enterprise auth (SAML/OIDC)
- ❌ Compliance (SOC2, GDPR)

## **Practical Technical Decisions**

| **Decision** | **Choice** | **Rationale** |
| --- | --- | --- |
| **Backend** | FastAPI + Uvicorn | Async I/O, auto OpenAPI docs, type safety |
| **Frontend** | React | Transfer from the Figma design |
| **Database** | SQLite | Simple MVP, scales to prod |
| **Auth** | API keys (JWT) | Simple enterprise standard |

**Why NOT:**

- Flask/Django: Too heavy for microservice
- Self-hosted: Focus on product, not infra

## **Architecture Diagram (Simplified)**

![Architecture Diagram](images/Architecture_Diagram.png)

**Data Flow:**

1. Client POSTs to `/predict` → FastAPI extracts features
2. Isolation Forest flags anomalies → Risk engine scores
3. WebSocket pushes live updates to dashboard
4. Threshold breach → Alerting triggers

**Deployment:** Single Docker Compose stack (FastAPI + Streamlit + DB)
