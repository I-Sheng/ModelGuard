# T-01 HMAC Integrity Runbook — ModelGuard AI

- Threat: T-01 — Batch Data Injection via Forged or Missing Signature
- Last Updated: 2026-05-31
- Related: `Threat_Model.md`, `Failed_Security_Tests_Runbook.md`, `Oncall_Runbook.md`

---

## Background

`POST /batch/analyze` requires every request to carry an `X-Batch-Signature: sha256=<hexdigest>` header. The backend computes `HMAC-SHA256(BATCH_HMAC_SECRET, raw_request_body)` and compares it with `hmac.compare_digest`. A mismatch returns `401 Invalid batch signature` and emits a `HMAC_SIGNATURE_FAILURE` log line containing the `partner_id` and `api_user` for operator investigation.

If this control fails — misconfigured secret, stale image, or bypassed dependency — a partner can submit falsified query records to suppress a CRITICAL theft score or fabricate benign audit history.

Mock payloads for this incident are in `tests/fixtures/hmac-batch-fixtures.ts`:

| Export | Represents |
|---|---|
| `VALID_HMAC_BATCH` | Legitimate partner batch; sign with the HMAC helper before submitting |
| `TAMPERED_BATCH` | Attacker-replaced records (low-risk decoys); accompanied by `FORGED_SIGNATURE` |
| `FORGED_SIGNATURE` | A plausible-looking but incorrect hex digest; should always get `401` |

---

## Possible Causes of a Wrong HMAC

### Misconfiguration

**Wrong or missing secret** — The partner is signing with a different `BATCH_HMAC_SECRET` than what the backend has. This happens when:
- The `.env` on the partner side was never updated after the secret rotated
- The backend container was restarted with a new secret but the partner wasn't notified
- `BATCH_HMAC_SECRET` is empty on one side — the backend returns `500 Batch signing not configured` in that case

### Implementation bugs on the partner side

**Body serialization mismatch** — The signature must be computed over the exact bytes that get sent. Common ways this goes wrong:
- Partner computes HMAC over a Python `dict` (`str(payload)`) but sends JSON — they're different bytes
- Partner uses `json.dumps(payload)` with different settings than the HTTP client (different key ordering, spacing, or unicode escaping)
- A different HTTP client serializes the JSON body differently from what the HMAC was computed over

**Encoding issues** — Partner computes HMAC over a UTF-8 string but the HTTP client sends Latin-1, or a trailing newline is added or removed before sending.

**Header format wrong** — The backend expects `sha256=<hex>`. Sending just `<hex>` or `SHA256=<hex>` fails the prefix check before the digest is even compared.

### Deliberate tampering (the T-01 threat)

**Body modified in transit** — Someone between the partner and the backend (a proxy, a compromised integration layer) altered the query records after the signature was computed. This is the `TAMPERED_BATCH` scenario — the signature is real but it belongs to the original body, not the modified one.

**Forged signature** — An attacker submits a made-up hex string as the signature without knowing the secret. This is `FORGED_SIGNATURE` — it looks plausible but won't match any real HMAC.

### How to tell which reason it is

| Observation | Likely cause |
|---|---|
| Backend logs `500 Batch signing not configured` | `BATCH_HMAC_SECRET` missing from backend env |
| `401` on every request from one partner | Partner has a wrong or stale secret |
| `401` on some requests but not others | Body serialization inconsistency on partner side |
| `HMAC_SIGNATURE_FAILURE` shows a `partner_id` that doesn't match any known integration | Forged / attacker-originated request |
| Sudden `401` after a deployment | Secret rotated without notifying the partner |

---

## Phase 1 — Detection

### 1.1 Run the T-01 security tests

The primary alert is `security.test.ts` reporting a failure on the T-01 block:

```bash
cd tests && bun test security.test.ts --verbose
```

The test suite sends two mock requests to `/batch/analyze`:

| Request | Payload | Signature | Expected |
|---|---|---|---|
| Forged | `TAMPERED_BATCH` | `FORGED_SIGNATURE` (wrong) | `401` |
| Valid | `VALID_HMAC_BATCH` | Correct HMAC-SHA256 | `200` |

**Failure means**: the forged request returned `200` — the HMAC check is not enforced.

### 1.2 Grep for signature failures in logs

If a forged batch was submitted against a running stack, the backend emits a structured warning:

```bash
docker compose logs --tail=500 backend | grep HMAC_SIGNATURE_FAILURE
```

Each line looks like:

```
2026-05-31 09:14:22 WARNING HMAC_SIGNATURE_FAILURE partner_id=openai-demo api_user=partner1
```

This tells you:
- **`partner_id`** — the business entity whose data was tampered (`openai-demo`)
- **`api_user`** — the authenticated API account that sent the request (`partner1`)

### 1.3 Verify the HMAC check is wired in source

```bash
grep -n "verify_batch_signature\|BATCH_HMAC_SECRET\|hmac.compare_digest" api/main.py
```

Confirm all four lines are present:

| Line | Expected content |
|---|---|
| Secret load | `BATCH_HMAC_SECRET = os.getenv("BATCH_HMAC_SECRET", "")` |
| Dependency | `async def verify_batch_signature(request: Request)` |
| Digest compare | `hmac.compare_digest(sig_header, expected)` |
| Route wiring | `_sig: None = Depends(verify_batch_signature)` in `batch_analyze` |

### 1.4 Check BATCH_HMAC_SECRET is set

A missing secret causes every `/batch/analyze` call to return `500 Batch signing not configured`:

```bash
docker compose logs --tail=200 backend | grep "Batch signing not configured"
```

If this line appears, the secret is absent — skip to Phase 2.1.

### 1.5 Confirm the running image is current

```bash
docker inspect modelguard-backend-1 --format '{{.Created}}'
```

Compare against the commit that introduced `verify_batch_signature`. If the image predates that commit, the container is running stale code — skip to Phase 2.2.

---

## Phase 2 — Response

### 2.1 Identify the offending partner and API user

From the `HMAC_SIGNATURE_FAILURE` log line collected in step 1.2:

```
HMAC_SIGNATURE_FAILURE partner_id=openai-demo api_user=partner1
```

- `partner_id` is the party whose batch data was tampered.
- `api_user` is the authenticated account that submitted it — use this to contact or escalate to the partner's technical team.

If multiple `HMAC_SIGNATURE_FAILURE` lines appear, group them by `partner_id` and `api_user` to scope the incident:

```bash
docker compose logs --tail=1000 backend \
  | grep HMAC_SIGNATURE_FAILURE \
  | awk '{print $NF, $(NF-1)}' \
  | sort | uniq -c | sort -rn
```

### 2.2 Suspend the offending partner

Once you have confirmed the `partner_id`, obtain an admin token and call the suspend endpoint:

```bash
source .env
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" | jq -r .access_token)

curl -s -X POST http://localhost:8000/admin/partners/openai-demo/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Expected response:

```json
{ "partner_id": "openai-demo", "status": "suspended" }
```

From this point on, any `POST /batch/analyze` with `partner_id=openai-demo` returns `403 Partner is suspended` — queries are not processed.

### 2.3 Verify the suspension is active

Check the suspended list:

```bash
curl -s http://localhost:8000/admin/partners/suspended \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Attempt a batch submission as the partner — it must fail with `403`:

```bash
source .env
PARTNER_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=${PARTNER1}&password=${PARTNER1_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" | jq -r .access_token)

curl -s -X POST http://localhost:8000/batch/analyze \
  -H "Authorization: Bearer $PARTNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Batch-Signature: sha256=aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899" \
  -d '{"partner_id":"openai-demo","window_start":"2026-01-01T00:00:00Z","window_end":"2026-01-01T01:00:00Z","queries":[]}' \
  | jq .detail
```

Expected: `"Partner is suspended"`

### 2.4 Scope accepted batches from the suspect window

If the HMAC check was inactive before the incident was detected, audit logs from that window are untrusted. In the backend logs, find the first unprotected submission:

```bash
docker compose logs backend | grep "POST /batch/analyze 200" | head -20
```

In OE Dashboard → **Audit Logs**: filter by `partner_id` and the suspect time window. Do not delete any records — preserve them for forensic review and note which batch IDs fall in the window.

### 2.5 Restore the HMAC check if it was absent

**Secret missing** — generate and set a new value:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Add the output to .env as: BATCH_HMAC_SECRET=<value>
docker compose up -d --force-recreate backend
```

Communicate the new secret to all partner integrations — they must update their signing key.

**Stale image** — rebuild and restart:

```bash
docker compose up --build -d backend
```

---

## Phase 3 — Recovery

### 3.1 Confirm HMAC enforcement is active

Run the T-01 security tests:

```bash
cd tests && bun test security.test.ts --verbose
```

Both assertions must pass:
- `TAMPERED_BATCH` with `FORGED_SIGNATURE` → `401`
- `VALID_HMAC_BATCH` with correct signature → `200`

### 3.2 Lift the suspension when investigation is complete

Once the partner's team has addressed the root cause and re-established a trusted signing integration:

```bash
curl -s -X DELETE http://localhost:8000/admin/partners/openai-demo/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Expected response:

```json
{ "partner_id": "openai-demo", "status": "active" }
```

Confirm the partner can now submit valid batches again by running the valid-HMAC fixture from the T-01 security test or resubmitting a known-good batch.

### 3.3 Run the full test suite for regressions

```bash
cd tests && bun test --verbose
```

All tests must pass before closing the incident.

### 3.4 Audit log integrity review

For any batch window where the HMAC check was inactive:

- OE Dashboard → **Audit Logs** → fetch the affected partner and time range.
- OE Dashboard → **Theft Reports** → check whether any HIGH/CRITICAL reports were filed for that window.
- If theft reports exist for the suspect window, treat the underlying query records as unverified — they may have been replaced with benign decoys.
- Notify the affected partner to re-submit authoritative logs for the suspect window if possible.

### 3.5 Document the incident

Record in the incident report:

- Time window the check was inactive (first unprotected request → fix deployed).
- `partner_id` and `api_user` from the `HMAC_SIGNATURE_FAILURE` log lines.
- Whether any HIGH/CRITICAL detections may have been suppressed during the window.
- Duration of suspension and outcome of partner investigation.
- Whether partner re-submission of authoritative logs is required.

---

## Severity Classification

| Severity | Condition | Response |
|---|---|---|
| **P1 — Critical** | HMAC check inactive AND audit logs show batch submissions during that window | Immediate rebuild; suspend the partner; preserve all logs; notify partner; escalate to security team |
| **P2 — High** | HMAC check inactive but no batch submissions detected during the window | Rebuild and re-verify within 15 minutes |
| **P3 — Medium** | Security test fails in CI but prod image is current and check is confirmed active | Investigate CI environment; no immediate prod action |

---

## Quick Reference

```bash
# Grep for forged-signature attempts
docker compose logs --tail=1000 backend | grep HMAC_SIGNATURE_FAILURE

# Suspend a partner (replace openai-demo with the actual partner_id)
curl -s -X POST http://localhost:8000/admin/partners/openai-demo/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# List all suspended partners
curl -s http://localhost:8000/admin/partners/suspended \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Lift a suspension
curl -s -X DELETE http://localhost:8000/admin/partners/openai-demo/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Run T-01 security tests only
cd tests && bun test security.test.ts --verbose

# Rebuild backend
docker compose up --build -d backend

# Generate a new BATCH_HMAC_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"
```
