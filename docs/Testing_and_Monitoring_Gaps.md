# Testing and Monitoring Gaps — ModelGuard AI

---

## Manual Tests (Not Automated)

The tests below require human judgment, labeled ground truth, or interaction with a live UI that cannot be driven via the API.

---

### MT-01 — OE Dashboard Visual Correctness

The Streamlit dashboard cannot be exercised by the functional test suite. The following must be verified manually after any change to `oe-dashboard/app.py`:

- All five pages render without a traceback: System Health, Statistics, Partner Activity, Audit Logs, Theft Reports.
- The Partner Activity bar chart renders correctly, with the 24 h threshold line visible and bars colored red/green by staleness.
- The sidebar "Live System Health" expander reflects the actual state of the running stack (not a stale cache).
- Selecting a theft report in the Theft Reports page loads the correct report detail, not a mismatched one.

**Why it cannot be automated:** Streamlit renders UI state server-side; the functional test suite only covers the backend API. There is no headless browser harness in CI.

---

### MT-02 — Detector Accuracy Against Simulated Extraction Campaigns

The functional test suite verifies that clearly normal traffic is not flagged (false-positive baseline). It does not verify that clearly abnormal traffic *is* flagged at the right level.

Manual procedure:
1. Craft a batch where one user sends 200+ queries with near-zero `unique_input_ratio` (< 0.05) and high `input_entropy` — a signature of systematic probing.
2. Submit via `POST /batch/analyze` and confirm the batch returns `HIGH` or `CRITICAL`.
3. Repeat with a different feature profile (high `query_count`, low `output_diversity`) and confirm escalation.

**Why it cannot be automated:** There is no labeled ground truth. Crafting a batch that *should* trigger a specific risk level requires human judgment about what the training distribution considers anomalous, and that judgment changes if the model is retrained.

---

### MT-03 — Adversarial Evasion Probing

An attacker who understands the five features (`query_count`, `unique_input_ratio`, `avg_input_length`, `input_entropy`, `output_diversity`) could craft batches that stay just inside the normal boundary across many windows, extracting model weights incrementally without ever triggering a HIGH alert.

Manual procedure:
1. Review the training distribution in `_TRAIN_DATA` (`api/main.py`) to identify the approximate normal feature centroid.
2. Craft a batch where each window stays within one standard deviation of the mean on all five features but collectively covers a large fraction of the model's output space.
3. Verify whether the detector ever escalates across repeated submissions.

**Why it cannot be automated:** Evasion requires iterative human red-teaming against the live model. A fixed test payload cannot capture the adaptive nature of a real attacker.

---

### MT-04 — Audit Log Tamper (T-02)

The threat model identifies that MinIO has no object lock. This cannot currently be asserted in a passing/failing test because the vulnerability is the *absence* of a control.

Manual procedure:
1. Submit a batch and record the audit log object key from `GET /audit/{partner_id}`.
2. Open the MinIO Console (`http://localhost:9001`) and delete or overwrite the object.
3. Confirm the API returns no record of the deleted entry and that no alert fires.

**Why it cannot be automated:** A test that passes only when a security control is absent is not a useful regression test. When WORM/object lock is added, this procedure should be re-run to confirm deletion is rejected by MinIO.

---

### MT-05 — Batch Injection Plausibility (T-01)

A partner can submit a batch containing entirely fabricated `input`/`output` records to suppress a real extraction that occurred in their system.

Manual procedure:
1. Authenticate as a partner.
2. Submit a batch with `queries` that do not correspond to any real traffic (synthetic `query_id` values, fabricated `input`/`output` strings that score LOW).
3. Confirm the API accepts the batch, stores the audit log, and returns `LOW` risk — even though the real traffic was never included.

**Why it cannot be automated:** There is no server-side integrity check to assert against. A test that verifies the vulnerability passes today by checking that falsified input is accepted; it would need to be rewritten once cryptographic batch signing (e.g., HMAC of the partner's query log) is implemented.

---

## Proactive Alert Metrics Not Yet in the OE Dashboard

The metrics below would improve early warning but are not currently surfaced anywhere in the dashboard.

---

### PM-01 — False Positive Rate

**What it would show:** Fraction of users flagged HIGH/CRITICAL who are later confirmed to be legitimate (flagged incorrectly).

**Why it is not in the dashboard:** This requires ground truth labels — a human or downstream system must confirm whether a flagged user was actually performing extraction. ModelGuard currently has no feedback loop from partner investigations back into the system. Without confirmed-legitimate labels, the rate cannot be computed.

---

### PM-02 — False Negative Rate

**What it would show:** Fraction of real extraction campaigns that were not flagged at HIGH or CRITICAL.

**Why it is not in the dashboard:** False negatives are invisible by definition — if the detector missed an attack, there is no record of the attack in the system to count. This rate can only be estimated via periodic red-team exercises (see MT-03) or post-incident review when a theft is discovered through other means.
