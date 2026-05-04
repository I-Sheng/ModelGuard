# Failed Security Tests Runbook — ModelGuard AI

- Status: MVP — Redesign v2
- Version: 0.3.0-oss
- Last Updated: 2026-05-03
- Related: `Threat_Model.md`, `High_Traffic_Runbook.md`, `Oncall_Runbook.md`

---

## Overview

A failing security test means a vulnerability was detected — the system did not protect against the threat under test. This runbook covers how to investigate, mitigate, and recover for each test currently in `tests/security.test.ts`.

**Convention:** Pass = no problem found. Fail = vulnerability active.

---

## Running the Tests

```bash
cd tests
bun test security.test.ts --verbose
```

Read credentials from `.env` — never hardcode them.

```bash
source ../.env
```

---

## ST-03 — Login Brute-Force Protection

**Test:** `20 consecutive failed logins trigger throttling or lockout`  
**File:** `tests/security.test.ts`  
**Threat ref:** T-03 (`Threat_Model.md`)

A failure means `/auth/login` accepted 20 rapid bad-password attempts without returning a single `429` or `403`. The brute-force / credential-stuffing path is open.

---

### Phase 1 — Investigate

**1.1 Confirm the rate limiter is running**

```bash
# Check slowapi is installed in the backend container
docker compose exec backend pip show slowapi

# Confirm the backend started without import errors
docker compose logs backend | grep -i "error\|slowapi\|limiter"
```

If slowapi is missing or the import failed, the limiter is not active — skip to Mitigate.

**1.2 Check whether requests are reaching the limiter**

```bash
# Tail live logs while re-running the test
docker compose logs -f backend &
cd tests && bun test security.test.ts --verbose
```

Look for repeated `POST /auth/login 401` lines with no `429` in between. If all return `401`, the limiter is not firing.

**1.3 Check the rate limit configuration in the source**

```bash
grep -n "limiter.limit\|Limiter\|RateLimitExceeded" api/main.py
```

Confirm:
- `limiter = Limiter(key_func=get_remote_address)` is present.
- `app.state.limiter = limiter` is set before middleware registration.
- `@limiter.limit("10/minute")` decorates `login()`.
- `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` is registered.

**1.4 Verify the backend image is current**

```bash
docker compose ps
docker inspect modelguard-backend | grep -i "created\|image"
```

If the image predates the slowapi commit, the container is running stale code.

---

### Phase 2 — Mitigate

**2.1 Stale image — rebuild and restart**

```bash
docker compose up --build -d backend
```

Re-run the test to confirm it now passes.

**2.2 Limiter misconfigured — patch and restart**

If the config check in 1.3 shows any piece is missing, edit `api/main.py` to restore it, then:

```bash
docker compose restart backend
cd tests && bun test security.test.ts --verbose
```

**2.3 Active brute-force in progress — immediate containment**

If the test failure coincides with suspicious login traffic in the logs (many `401` lines from a single source), treat this as an active attack:

```bash
# Identify the source IP from backend logs
docker compose logs --tail=500 backend | grep "POST /auth/login" | grep -oP '\d+\.\d+\.\d+\.\d+'| sort | uniq -c | sort -rn | head

# Block at the host firewall (replace <ip> with the attacker IP)
sudo iptables -I INPUT -s <ip> -j DROP
```

If a valid JWT was obtained before blocking, rotate the secret to invalidate all tokens (all users must re-login):

```bash
# Edit .env: generate a new JWT_SECRET_KEY value
docker compose restart backend
```

**2.4 High traffic compounding the exposure**

If the test fails during a traffic spike, coordinate with `High_Traffic_Runbook.md` Phase 2. The rate limiter is keyed by client IP — under distributed traffic, add an upstream `nginx limit_req_zone` or cloud WAF rule as a second layer:

```nginx
# nginx.conf snippet
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
location /auth/login {
    limit_req zone=login burst=5 nodelay;
}
```

---

### Phase 3 — Recover and Verify

**3.1 Confirm the fix**

```bash
cd tests && bun test security.test.ts --verbose
```

Expected output: `PASS — 20 consecutive failed logins trigger throttling or lockout`.

**3.2 Confirm legitimate login still works**

```bash
source .env
curl -s -X POST http://localhost:8000/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" | jq .role
```

Expected: `"admin"`. If this returns `429`, the rate limit is too aggressive for normal use — increase the threshold in `@limiter.limit("10/minute")` and redeploy.

**3.3 Run the full test suite for regressions**

```bash
cd tests && bun test --verbose
```

All tests must pass before closing the incident.

**3.4 Audit log gap check**

If the brute-force attack was sustained, check whether any legitimate sessions were disrupted:

```bash
# Review login activity in backend logs for the incident window
docker compose logs backend | grep "POST /auth/login" | grep -v "401"
```

**3.5 Document the incident**

Record in the incident report:
- Time window the test was failing.
- Whether an active attack was confirmed or suspected.
- Which mitigation step resolved it.
- Any audit log gaps or disrupted sessions.

---

## Test Summary

| Test | Threat | Fail means | Primary mitigation |
|---|---|---|---|
| 20 failed logins trigger throttling | T-03 | No rate limit on `/auth/login` | Rebuild backend image; verify slowapi config |
