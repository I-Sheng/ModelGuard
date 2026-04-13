# Security Test Documentation: ModelGuard AI

---

- Status: Initial
- Version: 0.1.0-oss
- Repository: I-Sheng/ModelGuard
- Last Updated: 2026-04-12
- Threat Model Reference: `Threat_Model.md`

---

## 1. Objectives

This document defines the initial security test plan for the ModelGuard AI MVP. Each test case maps to one or more threat IDs from `Threat_Model.md`. The goals are to:

1. Confirm which threats are currently exploitable (baseline evidence)
2. Verify mitigations as they are implemented
3. Provide reproducible steps so tests can be re-run after any code change

---

## 2. Test Environment

### Prerequisites

```bash
# Stack must be running
docker compose up -d

# Confirm API is up
curl -s http://localhost:8000/health | python3 -m json.tool

# Seed historical data for audit/report tests
docker compose exec api python seed_history.py
```

### Tools

| Tool | Purpose | Install |
|---|---|---|
| `curl` | HTTP requests | pre-installed on most systems |
| `python3` | Scripting multi-step tests | pre-installed |
| `mc` (MinIO Client) | Direct storage access tests | `docker run --rm -it --network host minio/mc` |
| `hey` or `ab` | Load / DoS tests | `apt install apache2-utils` or `go install github.com/rakyll/hey@latest` |
| browser | Dashboard auth tests | any |

### Conventions

- `API=http://localhost:8000`
- `MINIO_S3=http://localhost:9000`
- `MINIO_CONSOLE=http://localhost:9001`
- Test model ID used throughout: `security-test-model`
- Pass = observed behaviour matches **Expected Result**
- Fail = observed behaviour matches **Failure Indicator**

---

## 3. Test Cases

### Category A — Authentication and Authorization

---

#### ST-A01 — API accessible without any credentials

**Threat refs**: T-02  
**Severity**: Critical

**Objective**: Confirm that the API performs no authentication check and returns data to any unauthenticated caller.

**Steps**:
```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model_id":"security-test-model","query_text":"test","client_id":"anonymous"}'
```

**Expected Result (pass — confirms vulnerability)**: HTTP 200 with a full `prediction` + `risk_score` response body. No `401` or `403`.

**Failure Indicator**: HTTP 401 or 403 with an authentication challenge — would mean auth is already in place.

**Current Status**: FAIL (vulnerability confirmed, no mitigation deployed)

---

#### ST-A02 — Model registration open to any caller

**Threat refs**: T-02, T-03 (privilege escalation via open registration)  
**Severity**: High

**Objective**: Confirm any caller can register or overwrite a model without owning it.

**Steps**:
```bash
# Register a model as "ml-team"
curl -s -X POST http://localhost:8000/models/register \
  -H "Content-Type: application/json" \
  -d '{"model_id":"security-test-model","name":"Legit Model","version":"1.0","owner":"ml-team"}'

# Overwrite it as "attacker" without any credential
curl -s -X POST http://localhost:8000/models/register \
  -H "Content-Type: application/json" \
  -d '{"model_id":"security-test-model","name":"Rogue Model","version":"9.9","owner":"attacker"}'

# Confirm the overwrite succeeded
curl -s http://localhost:8000/models/security-test-model
```

**Expected Result (pass — confirms vulnerability)**: The `GET` response shows `"owner": "attacker"` and `"name": "Rogue Model"`.

**Failure Indicator**: Second registration is rejected with an ownership/auth error.

**Current Status**: FAIL (vulnerability confirmed)

---

#### ST-A03 — Audit logs readable by any caller

**Threat refs**: T-02, T-08  
**Severity**: High

**Objective**: Confirm that audit logs — which contain raw query text — are accessible without credentials.

**Steps**:
```bash
curl -s http://localhost:8000/audit/sentiment-v1 | python3 -m json.tool
```

**Expected Result (pass — confirms vulnerability)**: HTTP 200 listing all audit log keys. No auth required.

**Failure Indicator**: HTTP 401 or empty response behind an auth gate.

**Current Status**: FAIL (vulnerability confirmed)

---

#### ST-A04 — Attack reports readable by any caller

**Threat refs**: T-02, T-08  
**Severity**: High

**Objective**: Confirm attack report content (full query text + metadata) is accessible to any unauthenticated caller.

**Steps**:
```bash
# Get list of reports
REPORTS=$(curl -s http://localhost:8000/reports/sentiment-v1)
echo $REPORTS | python3 -m json.tool

# Extract one report key and fetch its content
KEY=$(echo $REPORTS | python3 -c "import sys,json; r=json.load(sys.stdin)['attack_reports']; print(r[0]['key'].split('/',1)[1])" 2>/dev/null)
curl -s "http://localhost:8000/reports/sentiment-v1/$KEY" | python3 -m json.tool
```

**Expected Result (pass — confirms vulnerability)**: Full report JSON including `query_text` returned with HTTP 200.

**Failure Indicator**: HTTP 401.

**Current Status**: FAIL (vulnerability confirmed)

---

### Category B — MinIO Storage Security

---

#### ST-B01 — Default credentials grant full storage access

**Threat refs**: T-01  
**Severity**: Critical

**Objective**: Confirm the default `minioadmin` / `minioadmin` credentials are active and give full access to all buckets and their contents via the MinIO web console.

**Steps**:
1. Open `http://localhost:9001` in a browser (or an incognito window).
2. At the MinIO login form, enter:
   - **Username**: `minioadmin`
   - **Password**: `minioadmin`
3. Click **Login**.
4. In the left sidebar, navigate to **Object Browser**.
5. Confirm all three buckets are listed: `modelguard-models`, `modelguard-auditlog`, `modelguard-reports`.
6. Click into `modelguard-models` — browse and open any model object to confirm read access.
7. Click into `modelguard-auditlog` — drill down through the date-partitioned folders and open any audit log JSON object to confirm full read access.
8. Click into `modelguard-reports` — browse and open any attack report object to confirm full read access.

**Expected Result (pass — confirms vulnerability)**: Login succeeds with the default credentials, all three buckets are visible, and objects inside each bucket can be read in full. No auth failure or access-denied message is shown.

**Failure Indicator**: Login is rejected — credentials have been rotated and the defaults are no longer valid.

**Current Status**: FAIL (vulnerability confirmed)

---

#### ST-B02 — Audit logs can be deleted via direct MinIO access

**Threat refs**: T-01, T-04  
**Severity**: High

**Objective**: Confirm that an attacker with MinIO credentials can delete audit logs, destroying the forensic trail.

**Steps**:
1. Open `http://localhost:9001` in a browser and log in with `minioadmin` / `minioadmin`.
2. In the left sidebar, navigate to **Object Browser** → `modelguard-auditlog`.
3. Drill into `sentiment-v1` → today's date folder and note the objects present.
4. Select any audit log object using its checkbox.
5. Click the **Delete** button and confirm the deletion prompt.
6. Verify the object no longer appears in the folder listing.
7. Open `http://localhost:8000/audit/sentiment-v1` in a new tab and confirm the deleted entry is absent from the API response.

**Expected Result (pass — confirms vulnerability)**: Object is deleted and no longer appears in the audit log listing.

**Failure Indicator**: Delete is rejected with an object-lock / WORM policy error.

**Current Status**: FAIL (vulnerability confirmed — no object lock)

---

#### ST-B03 — MinIO S3 API port bound to all interfaces

**Threat refs**: T-10  
**Severity**: Low (internal deployment) / Critical (cloud deployment)

**Objective**: Confirm MinIO is listening on `0.0.0.0` rather than `127.0.0.1`.

**Steps**:
1. Open `http://localhost:9001` in a browser and log in with `minioadmin` / `minioadmin`.
2. In the left sidebar, navigate to **Administrator** → **Configuration**.
3. Locate the **Server** section and inspect the displayed endpoint address — confirm it shows `0.0.0.0` or a wildcard interface rather than `127.0.0.1`.
4. As a secondary check, open a second browser tab and navigate to `http://localhost:9000` — if the S3 API responds (XML or JSON error page), the port is publicly reachable.

**Expected Result (pass — confirms vulnerability)**: The console configuration shows `0.0.0.0` as the bound address, and the S3 port at 9000 responds from the browser.

**Failure Indicator**: Port is bound to `127.0.0.1:9000` only.

**Current Status**: FAIL (vulnerability confirmed)

---

#### ST-B04 — MinIO console accessible without credentials challenge at network layer

**Threat refs**: T-01, T-05  
**Severity**: High

**Objective**: Confirm that the MinIO web console (port 9001) is reachable and presents only its own login form — no network-layer auth in front of it.

**Steps**:
1. Open a fresh incognito/private browser window to ensure no cached session is used.
2. Navigate to `http://localhost:9001`.
3. Observe whether the page loads and what is displayed.

**Expected Result (pass — confirms vulnerability)**: The MinIO login form loads immediately with no prior network-level block, firewall challenge, or VPN gate.

**Failure Indicator**: HTTP 403 or connection refused.

**Current Status**: FAIL (vulnerability confirmed)

---

### Category C — Injection and Input Validation

---

#### ST-C01 — Path traversal in model_id

**Threat refs**: T-02  
**Severity**: Medium

**Objective**: Confirm that `model_id` values containing path traversal sequences are sanitised before being used as MinIO object key prefixes.

**Steps**:
```bash
# Attempt to list objects outside the intended prefix
curl -s "http://localhost:8000/audit/..%2F..%2F" | python3 -m json.tool
curl -s "http://localhost:8000/audit/../modelguard-models" | python3 -m json.tool

# Attempt registration with traversal in model_id
curl -s -X POST http://localhost:8000/models/register \
  -H "Content-Type: application/json" \
  -d '{"model_id":"../../etc/passwd","name":"x","version":"1"}'
```

**Expected Result (pass — no vulnerability)**: HTTP 400/422 or the key is treated as a literal string with no traversal effect. No objects from unintended paths are returned.

**Failure Indicator**: Objects from a different bucket prefix are returned, or the registration succeeds and creates a key at an unintended path.

**Current Status**: Needs verification

---

#### ST-C02 — Oversized query payload

**Threat refs**: T-06  
**Severity**: Medium

**Objective**: Confirm the API handles very large `query_text` payloads without crashing or consuming unbounded memory.

**Steps**:
```python
import requests, json

payload = {
    "model_id": "security-test-model",
    "query_text": "A" * 10_000_000,  # 10 MB string
    "client_id": "test"
}
r = requests.post("http://localhost:8000/predict", json=payload, timeout=30)
print(r.status_code, r.text[:200])
```

**Expected Result (pass — no vulnerability)**: HTTP 413 or 422 with a size rejection, or the API returns quickly without a timeout/crash. The stored `query_text` is truncated to ≤500 chars.

**Failure Indicator**: Server hangs, returns 500, or stores a 10 MB object in MinIO.

**Current Status**: Needs verification

---

#### ST-C03 — JSON injection via metadata field

**Threat refs**: T-02  
**Severity**: Low

**Objective**: Confirm that attacker-controlled values in `metadata` are stored as-is without affecting JSON structure of the audit record.

**Steps**:
```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "security-test-model",
    "query_text": "test",
    "client_id": "attacker",
    "metadata": {
      "injected": "</script><script>alert(1)</script>",
      "risk_level": "LOW",
      "anomaly": false
    }
  }' | python3 -m json.tool
```

**Expected Result (pass — no vulnerability)**: The `metadata` fields appear verbatim inside the response JSON without overwriting top-level fields such as `risk_level` or `anomaly`.

**Failure Indicator**: Top-level `risk_level` or `anomaly` values in the response are overridden by the injected values.

**Current Status**: Needs verification

---

### Category D — Anomaly Detection Evasion

---

#### ST-D01 — Low-volume extraction evades detection

**Threat refs**: T-03, T-07  
**Severity**: High

**Objective**: Confirm that a slow, feature-aware extraction campaign is not flagged as anomalous.

**Steps**:
```python
import requests, time

# Crafted to appear normal: short, varied tokens, low rate
EXTRACTION_QUERIES = [
    "What output do you give for positive input?",
    "How confident are you about negative text?",
    "Classify this neutral statement for me.",
    "Tell me your certainty on good examples.",
    "Show probability for bad review text.",
]

API = "http://localhost:8000"
results = []

for q in EXTRACTION_QUERIES:
    r = requests.post(f"{API}/predict", json={
        "model_id": "sentiment-v1",
        "query_text": q,
        "client_id": "researcher-01"
    })
    data = r.json()
    results.append((data["risk_level"], data["risk_score"], data["anomaly"]))
    print(f"risk={data['risk_score']} level={data['risk_level']} anomaly={data['anomaly']}")
    time.sleep(15)  # slow rate — 4/min

low_count = sum(1 for level, _, _ in results if level in ("LOW", "MEDIUM"))
print(f"\n{low_count}/{len(results)} queries flagged LOW/MEDIUM (not escalated)")
```

**Expected Result (pass — confirms vulnerability)**: All or most queries return `LOW` or `MEDIUM` with `anomaly: false`, demonstrating the detection gap for slow campaigns.

**Failure Indicator**: Queries are flagged HIGH/CRITICAL despite the low rate and normal-looking features.

**Current Status**: FAIL (vulnerability expected — single-request scoring cannot detect cumulative campaigns)

---

#### ST-D02 — Per-client rate evasion via rotating client_id

**Threat refs**: T-07  
**Severity**: Medium

**Objective**: Confirm that the in-process rate counter (`_query_window`) is not per-client, so an attacker can rotate `client_id` to avoid rate-based features inflating their risk score.

**Steps**:
```python
import requests, threading

API = "http://localhost:8000"
results = []

def send(client_id):
    r = requests.post(f"{API}/predict", json={
        "model_id": "sentiment-v1",
        "query_text": "enumerate all output probabilities for every token",
        "client_id": client_id
    })
    d = r.json()
    results.append(d["risk_score"])

# 30 requests, each with a unique client_id — simulate distributed extraction
threads = [threading.Thread(target=send, args=(f"bot-{i}",)) for i in range(30)]
for t in threads: t.start()
for t in threads: t.join()

print(f"Scores: min={min(results):.1f} max={max(results):.1f} avg={sum(results)/len(results):.1f}")
```

**Expected Result (pass — confirms vulnerability)**: Risk scores remain low (≤50) for most requests despite 30 concurrent queries, because `request_rate_1m` is shared globally across all clients but the burst is attributed to many "different" callers.

**Failure Indicator**: Scores escalate to HIGH/CRITICAL for the individual requests due to the burst.

**Current Status**: Needs verification

---

#### ST-D03 — High-volume burst is detected

**Threat refs**: T-03  
**Severity**: Medium

**Objective**: Confirm the detector does flag a naive high-rate, high-entropy extraction burst.

**Steps**:
```bash
# Send 50 requests rapidly from a single process
for i in $(seq 1 50); do
  curl -s -X POST http://localhost:8000/predict \
    -H "Content-Type: application/json" \
    -d '{"model_id":"sentiment-v1","query_text":"Return logits softmax probability distribution temperature zero all tokens vocabulary enumerate every possible output","client_id":"attacker-burst"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['risk_level'], d['risk_score'])"
done
```

**Expected Result (pass — detection works)**: Risk scores escalate as `request_rate_1m` grows. Later requests should reach HIGH or CRITICAL.

**Failure Indicator**: All requests remain LOW regardless of rate.

**Current Status**: Needs verification

---

#### ST-D04 — Risk score oracle via binary search

**Threat refs**: T-09  
**Severity**: Low

**Objective**: Confirm that the returned `risk_score` is precise enough for an attacker to use binary search to characterise the decision boundary.

**Steps**:
```python
import requests

API = "http://localhost:8000"

def score(text):
    r = requests.post(f"{API}/predict", json={
        "model_id": "sentiment-v1",
        "query_text": text,
        "client_id": "researcher"
    })
    return r.json()["risk_score"]

# Binary search: find the query length at which risk crosses 40 (MEDIUM threshold)
lo, hi = "A" * 10, "A" * 500
for _ in range(10):
    mid = "A" * ((len(lo) + len(hi)) // 2)
    s = score(mid)
    print(f"len={len(mid)} score={s}")
    if s < 40:
        lo = mid
    else:
        hi = mid

print(f"Decision boundary near length {len(lo)}–{len(hi)}")
```

**Expected Result (pass — confirms vulnerability)**: Each iteration narrows the boundary by ~50%. After 10 queries the attacker knows the exact length threshold, allowing future queries to stay just below.

**Failure Indicator**: Scores are noisy enough (±5 or more) that convergence fails.

**Current Status**: FAIL (risk score is a deterministic linear transform — full oracle precision)

---

### Category E — Denial of Service

---

#### ST-E01 — No rate limiting on API endpoints

**Threat refs**: T-06  
**Severity**: High

**Objective**: Confirm the API applies no rate limiting and will process arbitrarily many requests per second.

**Steps**:
```bash
# Requires apache2-utils: apt install apache2-utils
ab -n 500 -c 50 -p /tmp/payload.json -T application/json \
   http://localhost:8000/predict

# Create payload file first:
echo '{"model_id":"security-test-model","query_text":"test","client_id":"loadtest"}' > /tmp/payload.json
```

**Expected Result (pass — confirms vulnerability)**: All 500 requests return HTTP 200. No HTTP 429 (Too Many Requests) is observed.

**Failure Indicator**: HTTP 429 responses after a threshold is exceeded.

**Current Status**: FAIL (no rate limiting middleware deployed)

---

#### ST-E02 — Storage exhaustion via audit log flooding

**Threat refs**: T-06  
**Severity**: Medium

**Objective**: Confirm that continuous requests create MinIO objects without bound, and that write failures are silently swallowed.

**Steps**:
```bash
# Step 1: Record current object count
BEFORE=$(docker run --rm --network host minio/mc \
  ls --recursive local/modelguard-auditlog/ 2>/dev/null | wc -l)
echo "Objects before: $BEFORE"

# Step 2: Send 200 requests
for i in $(seq 1 200); do
  curl -s -X POST http://localhost:8000/predict \
    -H "Content-Type: application/json" \
    -d '{"model_id":"security-test-model","query_text":"flood test '$i'","client_id":"flood"}' \
    > /dev/null
done

# Step 3: Count objects after
AFTER=$(docker run --rm --network host minio/mc \
  ls --recursive local/modelguard-auditlog/ 2>/dev/null | wc -l)
echo "Objects after: $AFTER  (added $(( AFTER - BEFORE )))"
```

**Expected Result (pass — confirms vulnerability)**: ~200 new objects created with no quota enforcement.

**Failure Indicator**: Object count stops growing at a configured bucket quota limit.

**Current Status**: FAIL (no MinIO bucket size quota configured)

---

### Category F — Information Disclosure

---

#### ST-F01 — Dashboard accessible without authentication

**Threat refs**: T-05  
**Severity**: High

**Objective**: Confirm the Streamlit dashboard exposes all model, audit, and report data to any unauthenticated browser.

**Steps**:
1. Open `http://localhost:8501` in a browser (or an incognito window with no prior session).
2. Navigate to **Audit Logs**, enter `sentiment-v1`, click **Fetch Logs**.
3. Navigate to **Attack Reports**, enter `sentiment-v1`, click **Fetch Reports**.
4. Select any report and view its full content.

**Expected Result (pass — confirms vulnerability)**: All pages load and return data with no login prompt.

**Failure Indicator**: A login page is presented before any data is visible.

**Current Status**: FAIL (no dashboard authentication)

---

#### ST-F02 — Internal error messages leak stack traces

**Threat refs**: T-02  
**Severity**: Low

**Objective**: Confirm that malformed requests do not trigger unhandled exceptions that expose internal file paths, library versions, or stack traces.

**Steps**:
```bash
# Send deliberately malformed JSON
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model_id": null, "query_text": 12345}'

# Send unexpected content type
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: text/plain" \
  -d 'not json at all'

# Send empty body
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d ''
```

**Expected Result (pass — no vulnerability)**: HTTP 422 responses with a structured Pydantic validation error. No Python tracebacks, file paths, or library internals in the response body.

**Failure Indicator**: HTTP 500 with a stack trace, absolute file path (e.g., `/usr/local/lib/python3.11/...`), or library version exposed in the body.

**Current Status**: Needs verification

---

#### ST-F03 — PII stored in audit logs via query text

**Threat refs**: T-08  
**Severity**: Medium

**Objective**: Confirm that sensitive text submitted in `query_text` is stored verbatim (up to 500 chars) in MinIO audit records.

**Steps**:
```bash
# Submit a query containing a fake PII string
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"model_id":"security-test-model","query_text":"My SSN is 123-45-6789 and email is test@example.com","client_id":"pii-test"}'

# Wait briefly, then check audit logs via API
curl -s "http://localhost:8000/audit/security-test-model" | python3 -m json.tool
```

Then fetch the stored object directly from MinIO:
```bash
docker run --rm --network host minio/mc \
  cat "local/modelguard-auditlog/security-test-model/$(date +%Y-%m-%d)/$(
    docker run --rm --network host minio/mc ls \
      local/modelguard-auditlog/security-test-model/$(date +%Y-%m-%d)/ 2>/dev/null \
      | tail -1 | awk '{print $NF}'
  )"
```

**Expected Result (pass — confirms vulnerability)**: The stored JSON contains `"query_text": "My SSN is 123-45-6789 and email is test@example.com"` verbatim.

**Failure Indicator**: The stored `query_text` is hashed, redacted, or absent.

**Current Status**: FAIL (vulnerability confirmed — only length-truncation applied, no redaction)

---

## 4. Test Execution Summary

| ID | Category | Threat Refs | Severity | Status |
|---|---|---|---|---|
| ST-A01 | Auth | T-02 | Critical | FAIL |
| ST-A02 | Auth | T-02 | High | FAIL |
| ST-A03 | Auth | T-02, T-08 | High | FAIL |
| ST-A04 | Auth | T-02, T-08 | High | FAIL |
| ST-B01 | Storage | T-01 | Critical | FAIL |
| ST-B02 | Storage | T-01, T-04 | High | FAIL |
| ST-B03 | Storage | T-10 | Low–Critical | FAIL |
| ST-B04 | Storage | T-01, T-05 | High | FAIL |
| ST-C01 | Injection | T-02 | Medium | Needs verification |
| ST-C02 | Injection | T-06 | Medium | Needs verification |
| ST-C03 | Injection | T-02 | Low | Needs verification |
| ST-D01 | Evasion | T-03, T-07 | High | FAIL |
| ST-D02 | Evasion | T-07 | Medium | Needs verification |
| ST-D03 | Evasion | T-03 | Medium | Needs verification |
| ST-D04 | Evasion | T-09 | Low | FAIL |
| ST-E01 | DoS | T-06 | High | FAIL |
| ST-E02 | DoS | T-06 | Medium | FAIL |
| ST-F01 | Info Disclosure | T-05 | High | FAIL |
| ST-F02 | Info Disclosure | T-02 | Low | Needs verification |
| ST-F03 | Info Disclosure | T-08 | Medium | FAIL |

**Total**: 20 test cases — 13 confirmed FAIL, 4 need verification, 3 need re-run after mitigation.

---

## 5. Mitigation Verification Checklist

Once mitigations from `Threat_Model.md` are implemented, re-run the corresponding tests and update their status to PASS.

| Mitigation | Re-run Tests | Pass Criteria |
|---|---|---|
| M-01: Rotate MinIO credentials | ST-B01, ST-B02, ST-B04 | Default `minioadmin` credentials rejected |
| M-02: Add API key auth | ST-A01, ST-A02, ST-A03, ST-A04 | Requests without valid key return HTTP 401 |
| M-03: Bind MinIO to 127.0.0.1 | ST-B03 | Port 9000/9001 not reachable from external interface |
| M-04: Dashboard auth | ST-F01 | Login required before any page loads |
| M-05: MinIO object lock (WORM) | ST-B02 | Delete attempt returns a retention policy error |
| M-06: Rate limiting middleware | ST-E01, ST-E02 | HTTP 429 returned after threshold; DoS flood stops growing |
| M-07: Per-client rate tracking | ST-D02 | Rotating `client_id` no longer defeats rate feature |
| M-08: Query text redaction | ST-F03 | Stored `query_text` is hashed or absent |
| M-09/M-10: Extended feature vector | ST-D01 | Slow extraction campaigns reach MEDIUM or higher |
| M-11: Risk score noise | ST-D04 | Binary search fails to converge within 10 queries |
