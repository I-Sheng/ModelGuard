# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Credential Rule

**Whenever you need a username or password — in any file, test, script, or command — read it from `.env`. Never write credentials in plaintext.**

```python
from dotenv import dotenv_values
_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
password = _ENV["ADMIN_PASSWORD"]
```

This applies to all code: test parametrize values, curl examples in scripts, seed scripts, and any other context where a real credential is referenced.

## Common Commands

```bash
# Start the full stack
docker compose up --build

# Stop (keep MinIO data volume)
docker compose down

# Stop and delete all data
docker compose down -v

# Seed demo audit history into MinIO
docker compose exec backend python seed_history.py

# Run smoke test
bash demo.sh
```

### Running tests

Tests live in `api/` and use `pytest` with `TestClient` (no live services needed — MinIO is mocked).

```bash
# Install test dependencies locally
pip install -r api/requirements.txt pytest

# Run all tests
pytest api/

# Run a single test file
pytest api/test_security.py

# Run a single test
pytest api/test_security.py::TestT01ArtifactOverwrite::test_cross_owner_upload_accepted
```

## Credentials and Environment

All credentials are stored in `.env` (gitignored). Copy `.env.example` to `.env` before first run.

## Architecture

Five Docker services wired together in `docker-compose.yml`:

| Service | Port | Description |
|---|---|---|
| `backend` | 8000 | FastAPI app — all business logic lives here |
| `frontend` | 3000 | nginx serving Swagger UI; fetches a role-scoped OpenAPI spec post-login |
| `oe-dashboard` | 8501 | Streamlit ops dashboard; auto-logins as admin on startup |
| `minio` | 9000/9001 | S3-compatible object storage (3 buckets: models, auditlog, reports) |
| `minio-init` | — | One-shot bootstrap that creates the three buckets, then exits |

### Backend (`api/main.py`)

Everything is in a single file. Key sections in order:

1. **JWT + RBAC** — `_create_token`, `get_current_user`, `require_role`. Three roles: `ml_user`, `customer`, `admin`. Dependency helpers `_ANY_AUTHED` and `_CUSTOMER` are reused across route definitions.
2. **Isolation Forest detector** — trained once at startup on 500 synthetic samples (`_TRAIN_DATA`). Four features per query: `query_length`, `unique_token_ratio`, `shannon_entropy`, `request_rate_1m`. The global `_query_window` list tracks request timestamps for rate estimation — it is **process-global, not per-client**.
3. **MinIO helpers** — `store_audit_log` writes every query; `store_attack_report` is called as a background task for HIGH/CRITICAL events only.
4. **Two detection endpoints** — `POST /analyze` (detection only) and `POST /predict` (mock sentiment inference + detection). Both run the same pipeline internally.
5. **Role-scoped OpenAPI** — four filtered spec endpoints (`/openapi-ml.json`, `/openapi-customer.json`, `/openapi-admin.json`, `/openapi-public.json`) served to the frontend after login.

### OE Dashboard (`oe-dashboard/app.py`)

Streamlit app that calls the backend API using an admin JWT obtained at startup. It does not connect to MinIO directly — all data comes through the backend.

## Threat Model

Three active threats in `Threat_Model.md`:

- **T-01** — Model artifact overwrite: `POST /models/{model_id}/upload` has no ownership check; any authenticated customer can overwrite another user's artifact.
- **T-02** — Mutable audit logs: MinIO has no object lock (WORM), so audit logs that feed attack report generation can be deleted or modified.
- **T-03** — No rate limiting: no middleware on any endpoint; `/predict` can be flooded to exhaust storage; `/auth/login` has no lockout.

Security tests in `api/test_security.py` assert that each vulnerability currently exists (tests will start failing once mitigations are applied).
