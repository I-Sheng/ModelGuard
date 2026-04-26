# High Traffic Incident Runbook — ModelGuard AI

- Status: MVP
- Threat: T-03 — No Rate Limit on Any Endpoint
- Last Updated: 2026-04-26

---

## Background

ModelGuard has no rate-limiting middleware on any endpoint (T-03). High-volume traffic against `/predict` exhausts MinIO write capacity and fills `modelguard-auditlog` until disk is exhausted — at which point the API silently continues without storing logs, creating a detection blind spot. High volume against `/auth/login` enables unlimited credential stuffing attempts. Arbitrarily large `query_text` payloads compound both impacts.

Relevant code: `api/main.py` — `_query_window` (line ~147) is process-global, not per-client, so it cannot distinguish one high-volume source from many.

> **Important:** Elevated traffic is not self-evidently malicious. It may be a legitimate usage spike, a misbehaving client, a bot, or a deliberate flood. The identification phase must establish which before you take any blocking action.

---

## Phase 1 — Identification

### 1.1 Confirm disruption is traffic-driven

Run in order. You are answering: *Is this a traffic problem or a compute/crash problem?*

```bash
# Container health — if backend is down for another reason, go to Oncall_Runbook.md instead
docker compose ps

# CPU and memory per container right now
docker stats --no-stream

# Tail live backend logs — look for request floods or write errors
docker compose logs -f backend
```

**Signals that point to a traffic problem, not a crash:**

- Backend container is running (`Up`) but response times are degraded or 503s appear
- `docker stats` shows backend CPU pegged near 100% or memory climbing steadily
- Log lines repeat rapidly with the same or rotating `client_id` values
- Log lines contain `minio write failed` or `audit_log_key: minio-unavailable` — MinIO is saturated

If the backend is crashed or MinIO is down for a non-traffic reason, follow `Oncall_Runbook.md` first.

---

### 1.2 Measure traffic volume and sources

```bash
# Count requests per second in the last 200 log lines
docker compose logs --tail=200 backend | grep -oP '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' | sort | uniq -c | sort -rn | head -20

# Unique client_id values in recent logs (high cardinality = many sources)
docker compose logs --tail=500 backend | grep -oP '"client_id":\s*"\K[^"]+' | sort | uniq -c | sort -rn | head -20

# Endpoint breakdown — which route is being hit?
docker compose logs --tail=500 backend | grep -oP '"(POST|GET) /\S+' | sort | uniq -c | sort -rn

# Payload size signal — look for anomalously large query_length values
docker compose logs --tail=200 backend | grep "query_length" | grep -oP '"query_length":\s*\K[\d.]+'| sort -n | tail -20
```

**Use OE Dashboard as a second source:**

- Open `http://localhost:8501` → **Audit Logs** → fetch the last 30 minutes
- Sort by `request_rate_1m` descending — values > 20 from a single `client_id` indicate a burst
- Filter by `risk_score = HIGH or CRITICAL` — a traffic flood produces a dense cluster here

---

### 1.3 Classify the source

Answer these questions before choosing a response. The goal is to determine intent, not assume it.

| Question | Where to look | What you are deciding |
|---|---|---|
| Is traffic from one IP / one `client_id`? | Backend logs, Audit Logs table | Concentrated vs. distributed |
| Is the `client_id` a known registered user? | `api/main.py` `USERS` dict or your user store | Legitimate user vs. unknown/bot |
| Are requests authenticated (carry a JWT)? | Log lines show `401` vs `200` | Whether the source has a valid account |
| Are payloads large (`query_length` > 1000)? | OE Dashboard feature vectors | Compute amplification — payload size matters |
| Are source IPs diverse? | Reverse-proxy / load balancer access logs | Single misbehaving client vs. many sources |
| Is this pattern consistent with a known release or event? | Team calendar, recent deploy history | Legitimate traffic spike vs. anomaly |

**Three likely outcomes after this step:**

1. **Known user, likely accident** — legitimate client misconfiguration or runaway script. Contact the user before blocking.
2. **Unknown or suspicious source** — no matching user, automated patterns, unusual hours. Proceed with rate limiting; escalate if it continues.
3. **Confirmed malicious** — credential stuffing patterns on `/auth/login`, extraction signatures in feature vectors (see `Oncall_Runbook.md` Scenario 4). Block and file incident report.

---

## Phase 2 — Response

### 2.1 Concentrated traffic from one source

**Step 1 — Determine intent before blocking.**

If the `client_id` maps to a known user, contact them first. A runaway integration test or misconfigured retry loop is the most common cause, and blocking a legitimate customer requires justification.

If the source is unrecognized or contact is not possible, proceed to Step 2.

**Step 2 — Apply a graduated rate limit (software layer).**

Until a proper middleware is deployed (see Phase 4), use `docker compose` resource limits as a circuit breaker:

```yaml
# docker-compose.yml — add under backend service
deploy:
  resources:
    limits:
      cpus: "1.0"
      memory: 512M
```

Restart the backend after editing:

```bash
docker compose up -d --force-recreate backend
```

This caps damage to the system but does not stop the traffic source.

**Step 3 — Block at the network layer (if source is confirmed hostile or unresponsive).**

If a reverse proxy (nginx, Traefik) or host firewall sits in front of the backend:

```bash
# iptables example — drop traffic from a single source IP
sudo iptables -I INPUT -s <source_ip> -j DROP
```

On Kubernetes or a cloud load balancer, add an ingress deny rule for the source IP.

**Step 4 — Revoke the JWT (if source holds a valid token).**

JWT revocation is not yet implemented in ModelGuard (tokens are stateless with a 60-minute TTL). Mitigations until revocation exists:

- Rotate `JWT_SECRET` in `.env` and restart the backend — this invalidates **all** tokens:
  ```bash
  # Edit .env: set JWT_SECRET to a new random value
  docker compose restart backend
  ```
  **Trade-off:** all legitimate users must re-login. Only use this if the token holder is confirmed hostile.

---

### 2.2 Distributed or high-volume traffic from many sources

**Step 1 — Check whether a cache layer can absorb traffic.**

ModelGuard currently has no HTTP cache. For read-heavy traffic against `/models` or `/health`, adding an nginx cache in front of the backend can reduce backend load without dropping requests.

**Step 2 — Scale out (horizontal).**

Spin additional backend replicas behind a load balancer:

```bash
docker compose up -d --scale backend=3
```

> Note: `_query_window` in `main.py` (line ~147) is process-global. With multiple replicas each process tracks its own window, so per-client rate detection becomes inaccurate. This is a known limitation under T-03 until a shared rate store (e.g., Redis) is added.

**Step 3 — Scale up (vertical).**

If the host has spare capacity, increase container resource ceilings in `docker-compose.yml` under the backend `deploy.resources.limits` block.

**Step 4 — Upstream network-layer mitigation.**

For volumetric floods that saturate the host NIC, software-layer responses are insufficient. Escalate to:

- Cloud provider protection (AWS Shield, Cloudflare, etc.)
- Null-route or anycast scrubbing at the network edge
- Contact your ISP if on bare metal

**Step 5 — Shed non-essential load.**

While under high load, reduce MinIO write pressure by temporarily disabling background audit log writes. This preserves API availability at the cost of audit coverage — document the outage window.

---

### 2.3 Server overwhelmed with compute (not purely request volume)

This occurs when large `query_text` payloads drive high CPU on the Isolation Forest scorer, regardless of how many unique sources are sending them.

**Step 1 — Identify the payload size.**

```bash
docker compose logs --tail=200 backend | grep "query_length" \
  | grep -oP '"query_length":\s*\K[\d.]+' | awk '{sum+=$1; n++} END {print "avg:", sum/n}' 
```

**Step 2 — Enforce a payload size limit.**

In `api/main.py`, add a `max_length` validator to `QueryRequest` and `PredictRequest`:

```python
query_text: str = Field(..., max_length=2000)
```

Restart the backend to apply:

```bash
docker compose restart backend
```

**Step 3 — Horizontal or vertical scale** (same as 2.2 Steps 2–3).

---

## Phase 3 — Recovery and Verification

### 3.1 Confirm service is restored

```bash
# Basic health (no auth)
curl http://localhost:8000/health

# Detailed health (requires token — read credentials from .env)
source .env
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=${ADMIN_PASSWORD}" | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/health/detail | jq .
```

Expected: `"status": "ok"`, `"minio": "connected"`, `"detector": "loaded"`.

OE Dashboard: open `http://localhost:8501` → **System Health** → all four indicators green.

### 3.2 Audit log gap check

High traffic may have exhausted MinIO before the backend stopped accepting requests — audit records will be missing for that window.

- OE Dashboard → **Audit Logs** → enter the affected model ID and the incident time range → Fetch.
- Any gap (no entries for a span that had traffic) = lost audit records. Note the window in the incident report.

### 3.3 Security tests

Run the full test suite to confirm no regressions were introduced during mitigation changes:

```bash
pytest api/
```

T-03 tests assert the vulnerability currently exists. If you deployed a rate-limit fix, update `api/tests/test_security.py` accordingly and confirm the test now fails in the expected direction before committing.

---

## Phase 4 — Automation Opportunities

The runbook above can be 100% automated. Priority order:

| Step | Automation approach | Effort |
|---|---|---|
| Traffic spike detection | Prometheus + Alertmanager rule on `http_requests_total` rate > threshold | Low |
| Payload size enforcement | `Field(max_length=2000)` in Pydantic models — one-line fix | Trivial |
| Per-IP rate limiting | slowapi or starlette middleware; or nginx `limit_req_zone` | Low |
| Per-client JWT rate limiting | Move `_query_window` to Redis (keyed by `client_id`) | Medium |
| Auto-scale on load | Kubernetes HPA targeting CPU utilization | Medium |
| IP blocklist | Fail2ban watching backend logs; or WAF rule | Low |
| Audit log WORM protection | Enable MinIO object lock on `modelguard-auditlog` bucket (also fixes T-02) | Low |
| Incident ticket creation | Alertmanager webhook → PagerDuty / Linear | Low |

---

## Severity and Escalation

| Severity | Condition | Response time | Action |
|---|---|---|---|
| **P1 — Critical** | Backend returning 5xx to legitimate users; MinIO writes failing | Immediate | Execute Phase 2 response; notify team; document audit gap |
| **P2 — High** | Elevated error rate but service partially available; `request_rate_1m` > 50 sustained | < 15 min | Rate-limit the source; monitor recovery |
| **P3 — Medium** | High volume from one source; other users unaffected | < 1 hour | Contact source if known; block if unresponsive; file incident report |
| **P4 — Low** | Anomaly spike resolved on its own; no MinIO write failures | Next business day | Review logs; add rate-limit rule proactively |

---

## Missing Information / Open Questions

The following information would improve this runbook and should be provided in the service header or incident brief:

1. **Reverse proxy / load balancer details** — Is nginx, Traefik, or a cloud LB in front of the backend? If yes, IP-level blocking and rate limiting belong there, not in the application.
2. **Deployment target** — Docker Compose single-host vs. Kubernetes vs. cloud container service. Scaling steps differ substantially.
3. **Shared rate store** — Is Redis available? Per-client rate limiting requires it (the current `_query_window` is process-local).
4. **Observability stack** — Is Prometheus/Grafana deployed? If yes, alerting can be wired directly to this runbook's triggers.
5. **On-call contact list** — Who owns network-layer escalation (cloud provider, ISP null-routing)?
6. **JWT revocation strategy** — Until a token denylist or shorter TTL is implemented, rotating `JWT_SECRET` is the only revocation mechanism and it affects all users.
7. **Baseline traffic profile** — Without a known-normal baseline, "high traffic" has no quantitative threshold. Establishing p95/p99 request rates during normal operation is a prerequisite for meaningful alerting.
