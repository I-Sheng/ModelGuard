# Security Tests: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.3.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-05-03
- Threat Model Reference: `Threat_Model.md`

---

## Test Environment

### Prerequisites

```bash
# Stack must be running
docker compose up -d

# Confirm API is up
curl -s http://localhost:8000/health | python3 -m json.tool
```

### Conventions

- `API=http://localhost:8000`
- Pass = observed behaviour matches **Expected Result**
- Fail = observed behaviour matches **Failure Indicator**
- Credentials read from `.env` — never hardcoded

---

## Test Cases

### ST-01 — Batch Audit Log Deletion Corrupts Derived Theft Report

**Threat ref**: T-02  
**Severity**: High

**Objective**: Confirm that an attacker with MinIO credentials can delete a batch audit record and cause the derived theft report to silently omit the deleted events.

**Steps**:
```bash
source .env

# Step 1: Obtain an admin token
ADMIN_TOKEN=$(curl -s -X POST $API/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 2: Submit a HIGH-risk batch to generate an audit record and report
curl -s -X POST $API/batch/analyze \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "partner_id": "audit-tamper-test",
    "window_start": "2026-05-03T10:00:00Z",
    "window_end": "2026-05-03T11:00:00Z",
    "queries": [
      {"query_id": "q-001", "query_user": "thief", "input": "'"$(python3 -c "print('x'*500)")"'", "output": "result"},
      {"query_id": "q-002", "query_user": "thief", "input": "'"$(python3 -c "print('y'*500)")"'", "output": "result2"}
    ]
  }'

# Step 3: List audit records before deletion
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/audit/audit-tamper-test?date=$(date +%Y-%m-%d)" | python3 -m json.tool

# Step 4: Delete the audit record directly via MinIO
docker run --rm --network host minio/mc alias set local \
  http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}

docker run --rm --network host minio/mc rm --recursive --force \
  local/modelguard-auditlog/audit-tamper-test/$(date +%Y-%m-%d)/

# Step 5: List audit records after deletion
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/audit/audit-tamper-test?date=$(date +%Y-%m-%d)" | python3 -m json.tool
```

**Expected Result (pass — no problem)**: Step 5 raises an integrity error, or MinIO rejects the delete with a WORM retention policy error, and the audit record is still present.

**Failure Indicator**: Step 5 returns an empty list with no error — the audit record has been deleted without detection.

**Current Status**: FAIL (vulnerability active — no object lock on audit bucket; deletion succeeds silently)

---

### ST-02 — No Rate Limit on /batch/analyze Enables Storage Exhaustion

**Threat ref**: T-03  
**Severity**: Medium

**Objective**: Confirm the `/batch/analyze` endpoint applies no rate limiting and processes arbitrarily many requests per second, enabling MinIO write exhaustion and audit log blind spots.

**Steps**:
```bash
source .env

ADMIN_TOKEN=$(curl -s -X POST $API/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Write minimal batch payload to a temp file
cat > /tmp/batch_payload.json <<'EOF'
{
  "partner_id": "flood-test",
  "window_start": "2026-05-03T10:00:00Z",
  "window_end": "2026-05-03T10:01:00Z",
  "queries": [
    {"query_id": "q-001", "query_user": "u1", "input": "test input", "output": "test output"}
  ]
}
EOF

# Requires apache2-utils: apt install apache2-utils
ab -n 200 -c 20 \
  -p /tmp/batch_payload.json \
  -T application/json \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/batch/analyze
```

**Expected Result (pass — no problem)**: HTTP 429 responses appear after a configured threshold is exceeded.

**Failure Indicator**: All 200 requests return HTTP 200. No HTTP 429 is observed in the `ab` summary. MinIO gains ~200 new audit log objects.

**Current Status**: FAIL (no rate-limiting middleware deployed — all requests processed without throttling)

---

### ST-03 — No Rate Limit on /auth/login Enables Credential Stuffing

**Threat ref**: T-03  
**Severity**: Medium

**Objective**: Confirm the `/auth/login` endpoint applies no rate limiting or lockout after repeated failed attempts.

**Steps**:
```bash
source .env

# 20 consecutive failed login attempts
for i in $(seq 1 20); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST $API/auth/login \
    -d "username=${ADMIN_USER}&password=wrong_password_attempt_${i}")
  echo "Attempt $i: HTTP $STATUS"
done

# Confirm legitimate login still works
curl -s -X POST $API/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" | python3 -m json.tool
```

**Expected Result (pass — no problem)**: HTTP 429 or HTTP 423 (account locked) appears after a threshold of failed attempts (e.g., after attempt 10 or 15).

**Failure Indicator**: All 20 failed attempts return HTTP 401 with no 429 or lockout. Legitimate login continues to work immediately after the flood.

**Current Status**: FAIL (no lockout or rate limit on `/auth/login` — credential stuffing unimpeded)

---

## Test Execution Summary

| ID | Threat Ref | Severity | Status |
|---|---|---|---|
| ST-01 | T-02 | High | FAIL |
| ST-02 | T-03 | Medium | FAIL |
| ST-03 | T-03 | Medium | FAIL |

**Total**: 3 test cases — 3 confirmed FAIL.
