# Presentation Draft — T-01 Simulated Incident Walkthrough
## ModelGuard AI · Security Incident Response

Target: under 10 min (bonus). Hard cap: 15 min.

---

## Slide 1 — Title (0:30)

**T-01 Batch Data Injection**
Simulated Incident Walkthrough — ModelGuard AI

---

## Slide 2 — Simulation walkthrough (Live Demo)

**T-01 HMAC Integrity Runbook — `docs/T01_HMAC_Integrity_Runbook.md`**

*(Live walkthrough — show the three phases in the runbook while narrating)*

| Phase | Key Step |
|---|---|
| **1 — Detection** | OE Dashboard or `grep HMAC_SIGNATURE_FAILURE`; match to Possible Causes table |
| **2 — Response** | Identify `api_user` from log → suspend → verify 403 on a valid-HMAC request |
| **3 — Recovery** | `bun test` passes → review audit logs → lift suspension → document |

---

## Slide 3 — Preparedness Documents (1:30)

**Does T-01 Belong in Our Preparedness Docs?**

**Yes — all three.**

| Document | What it contributes |
|---|---|
| **Threat Model** (`Threat_Model.md`) | Names T-01 as highest-impact; defines attack vectors and STRIDE categories; informs severity rating |
| **Security Tests** (`Security_Tests.md` + `manual.test.ts`) | HMAC tests gate every deployment — CI fails if the control is removed, blocking a bad image before it ships |
| **Compliance Audit** (`Compliance_Audit.md`) | Records the HMAC control as evidence for **GDPR Art. 5(1)(d)**, **SOC 2 PI1**, and **NIST AI RMF Manage**; documents the known gap (`seed_history.py` bypasses the API) |

T-01 is the only threat that touches **all three documents** — it's the highest-impact, most fully mitigated threat in the system.

---

## Slide 4 — Similar Incidents / Pareto (1:30)

### T-02 — Mutable Audit Logs (same STRIDE family)
- T-01 protects the **API input boundary**; T-02 protects the **storage boundary**
- An attacker who deletes audit records in MinIO erases evidence that T-01 ever happened
- Same root cause pattern: **the system trusts data it should not**
- Mitigation: MinIO WORM object lock (30-day GOVERNANCE retention)

### Shared pattern
Both T-01 and T-02 are **input integrity failures** at different layers. A sophisticated attacker needs to defeat both to fully cover their tracks.

### Anticipated questions
- *"What if the partner signs falsified data with a valid key?"* → HMAC only detects tampering in transit or by a third party; a partner who generates a valid signature on forged records can still inject. Documented residual risk in the Threat Model.
- *"What if `BATCH_HMAC_SECRET` leaks?"* → Rotate: `python3 -c "import secrets; print(secrets.token_hex(32))"`, update `.env`, rebuild backend. Covered in the runbook Quick Reference.
- *"What if the attacker rotates api_user accounts?"* → Each JWT is tied to a verified user; multiple accounts require multiple credential breaches, each separately logged.

---

## Slide 5 — Summary (0:30)

**In Summary**

- **Detection:** OE Dashboard (live operator view) + CI security tests (pre-deploy gate)
- **Runbook:** 3 phases — Detect → Respond (suspend) → Recover (test + document)
- **Preparedness:** Lives in all three docs — Threat Model identified it, Security Tests gate it, Compliance Audit evidences it
- **Pareto:** T-01 and T-02 share the same integrity-failure root cause at different system layers

---

## Slide 6 — Thank You

Thank you for listening.

---

## Pre-Presentation Checklist

- [ ] Screenshot of OE Dashboard HMAC Signature Failures section ready for Slide 2
- [ ] Terminal open with `docker compose logs backend | grep HMAC_SIGNATURE_FAILURE` ready to run
- [ ] `docs/T01_HMAC_Integrity_Runbook.md` open in editor or browser for Slide 2
- [ ] Stack running: `docker compose up -d` and verify `http://localhost:8501` loads
- [ ] Know the "partner signs falsified data" residual risk answer cold (Slide 4)
