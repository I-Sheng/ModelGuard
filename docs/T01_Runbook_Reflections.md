# T-01 Runbook Reflections

## Were the steps easy to follow and understand?

Overall yes. The three-phase structure (Detection → Response → Recovery) matches the natural mental model of an incident, and each phase has numbered steps with copy-paste commands. The Possible Causes table is particularly useful during detection — being able to match an observation (e.g. "401 on some requests but not others") to a root cause category reduces guesswork under pressure.

---
## Can the runbook be simplified further?

- **Phase 2.1** has a `grep | awk | sort | uniq -c | sort -rn` pipeline that is easy to mistype under stress. It could move to the Quick Reference section as a named snippet, or become a `make` target (`make t01-suspects`).

---

## Steps that should be automated further

| Step | Current state | Suggested automation |
|---|---|---|
| 2.1 — identify offending user | Manual grep + awk pipeline | Script or `make` target that greps logs, extracts `api_user` values, and prints a ranked summary |
| 2.2 — suspend user | Manual curl after manually copying `api_user` from log output | Script that accepts `api_user` as an argument, sources `.env`, fetches an admin token, and posts the suspension in one command |
| Secret rotation | Manual: `python3 -c "..."; edit .env; rebuild` | A `make rotate-hmac-secret` target that generates a new secret, updates `.env`, and triggers `docker compose up --build -d backend` |

---

## Automated steps that need manual supplementation

- **Step 3.1 (`bun test`)** verifies that the HMAC enforcement code path passes tests, but it does not confirm that the running production container is built from the current image. A `docker inspect` or `docker compose ps` check to compare the image digest against the latest build should accompany this step before closing the incident.
- **Step 3.2 (deliberate vs. integration error)** is correctly left as a judgment call, but the runbook would benefit from a concrete evidence checklist: e.g., "three or more failures from the same `api_user` within five minutes = likely deliberate; one failure following a deployment = likely misconfiguration." Without that anchor, two operators might reach opposite conclusions from the same log.
