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

| Category | Cause | Observation |
|---|---|---|
| Misconfiguration | Wrong or missing `BATCH_HMAC_SECRET` — partner's key doesn't match the backend's | `401` on every request from one partner |
| Misconfiguration | Secret absent on the backend side | `500 Batch signing not configured` in logs |
| Misconfiguration | Secret rotated without notifying the partner | Sudden `401` after a deployment |
| Implementation bug | Body serialization mismatch — HMAC computed over different bytes than what was sent (e.g. different key ordering, spacing, or encoding) | `401` on some requests but not others |
| Implementation bug | Wrong header format — backend expects `sha256=<hex>`; sending bare `<hex>` fails the prefix check | `401` with `Missing or malformed` detail |
| Deliberate tampering | Body modified in transit — signature is real but belongs to the original unmodified body | `HMAC_SIGNATURE_FAILURE` log; known `api_user` |
| Deliberate tampering | Forged signature — attacker submits a made-up hex string without knowing the secret | `HMAC_SIGNATURE_FAILURE` log; unknown or suspicious `api_user` |

---

## Phase 1 — Detection

### 1.1 OE Dashboard — Partner Activity

Open the OE Dashboard and navigate to **Partner Activity**. Scroll to the **HMAC Signature Failures** section at the bottom of the page. Any invalid batch attempt is listed here with its timestamp, `api_user`, and `partner_id`.

### 1.2 Docker backend log

```bash
docker compose logs --tail=500 backend | grep HMAC_SIGNATURE_FAILURE
```

Each line looks like:

```
2026-05-31 09:14:22 WARNING HMAC_SIGNATURE_FAILURE partner_id=openai-demo api_user=bad-actor
```

- **`api_user`** — the authenticated account that sent the forged request; this is the target for suspension
- **`partner_id`** — the business entity named in the payload

---

## Phase 2 — Response

### 2.1 Identify the offending API user

From the `HMAC_SIGNATURE_FAILURE` log line collected in step 1.2:

```
HMAC_SIGNATURE_FAILURE partner_id=openai-demo api_user=bad-actor
```

- **`api_user`** is the authenticated API account that sent the request — this is the target for suspension. It is verified by JWT and cannot be spoofed.
- `partner_id` is the business entity named in the payload — useful context but user-supplied and not reliable for access control.

If multiple `HMAC_SIGNATURE_FAILURE` lines appear, group them by `api_user` to scope the incident:

```bash
docker compose logs --tail=1000 backend \
  | grep HMAC_SIGNATURE_FAILURE \
  | awk '{print $NF, $(NF-1)}' \
  | sort | uniq -c | sort -rn
```

### 2.2 Suspend the offending user

Once you have confirmed the `api_user`, obtain an admin token and call the user suspend endpoint:

```bash
source .env
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" | jq -r .access_token)

curl -s -X POST http://localhost:8000/admin/users/bad-actor/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Replace `bad-actor` with the `api_user` value from the log line.

Expected response:

```json
{ "username": "bad-actor", "status": "suspended" }
```

From this point on, any `POST /batch/analyze` from that user returns `403 User is suspended` — their queries are not processed regardless of what `partner_id` they supply.

### 2.3 Verify the suspension is active

Check the suspended users list:

```bash
curl -s http://localhost:8000/admin/users/suspended \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Attempt a batch submission as the suspended user — it must fail with `403`:

```bash
source .env
BAD_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=${BAD_ACTOR}&password=${BAD_ACTOR_PASSWORD}" \
  -H "Content-Type: application/x-www-form-urlencoded" | jq -r .access_token)

curl -s -X POST http://localhost:8000/batch/analyze \
  -H "Authorization: Bearer $BAD_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Batch-Signature: sha256=aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899" \
  -d '{"partner_id":"openai-demo","window_start":"2026-01-01T00:00:00Z","window_end":"2026-01-01T01:00:00Z","queries":[]}' \
  | jq .detail
```

Expected: `"User is suspended"`

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

Once the user's account has been investigated and cleared:

```bash
curl -s -X DELETE http://localhost:8000/admin/users/bad-actor/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

Expected response:

```json
{ "username": "bad-actor", "status": "active" }
```

Confirm the user can now submit valid batches again by running the valid-HMAC fixture from the T-01 security test or resubmitting a known-good batch.

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
| **P1 — Critical** | HMAC check inactive AND audit logs show batch submissions during that window | Immediate rebuild; suspend the offending user; preserve all logs; notify partner; escalate to security team |
| **P2 — High** | HMAC check inactive but no batch submissions detected during the window | Rebuild and re-verify within 15 minutes |
| **P3 — Medium** | Security test fails in CI but prod image is current and check is confirmed active | Investigate CI environment; no immediate prod action |

---

## Quick Reference

```bash
# Grep for forged-signature attempts
docker compose logs --tail=1000 backend | grep HMAC_SIGNATURE_FAILURE

# Suspend a user (replace bad-actor with the api_user from the log)
curl -s -X POST http://localhost:8000/admin/users/bad-actor/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# List all suspended users
curl -s http://localhost:8000/admin/users/suspended \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Lift a suspension
curl -s -X DELETE http://localhost:8000/admin/users/bad-actor/suspend \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# Run T-01 security tests only
cd tests && bun test security.test.ts --verbose

# Rebuild backend
docker compose up --build -d backend

# Generate a new BATCH_HMAC_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"
```
