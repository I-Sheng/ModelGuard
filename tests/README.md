# ModelGuard Functional Tests

TypeScript + Jest tests that hit the **live API** at `http://localhost:8000`.

## Prerequisites

- Bun 1.0+
- The full stack running via Docker Compose
- A `.env` file at the project root (copy from `.env.example`)

## Setup

```bash
# From the project root — start the stack
docker compose up --build

# From this directory — install dependencies
cd tests
bun install
```

## Running Tests

```bash
# Run all tests
bun test

# Run a specific test file
bun test security.test.ts

# Run with verbose output
bun test --verbose
```

## Test Files

| File | Description |
|---|---|
| `functional.test.ts` | RBAC enforcement — verifies role-based access control on live endpoints |
| `security.test.ts` | Security tests — asserts each threat mitigation is in place |

## What Is Tested

### `functional.test.ts` — RBAC

| Test | Endpoint | Actor | Expected |
|---|---|---|---|
| ml_user cannot access audit logs | `GET /audit/{model_id}` | `ml_user` | 403 |
| ml_user cannot access reports | `GET /reports/{model_id}` | `ml_user` | 403 |

## Credentials

Tests read `ML_USER`, `ML_USER_PASSWORD`, `CUSTOMER1`, `CUSTOMER1_PASSWORD`, `ADMIN_USER`, and `ADMIN_PASSWORD` from the project-root `.env` file. Never hardcode credentials.
