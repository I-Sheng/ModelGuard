# OE Dashboard — Operational Questions and Gaps

## Questions the Dashboard Currently Answers

### Service Availability
| Question | Page | Signal |
|---|---|---|
| Is the backend API responding? | System Health / sidebar | API tile = `OK` |
| Is the SwaggerUI frontend reachable? | System Health / sidebar | Frontend tile = `OK` |
| Is MinIO storage reachable? | System Health / sidebar | MinIO tile = `OK` |
| Is the Isolation Forest detector loaded? | System Health / sidebar | Detection Engine tile = `LOADED` |

### Platform Throughput
| Question | Page | Signal |
|---|---|---|
| How many partners are registered? | Statistics | Registered Partners counter |
| How many batches have been analyzed (cumulative)? | Statistics | Batches Analyzed counter |
| Which partners have not submitted a batch in the last 24 hours? | Partner Activity | STALE row + bar chart |
| When did each partner last submit a batch? | Partner Activity | `last_seen` + `hours_since_last_batch` columns |

### Detection History (per partner, manual lookup)
| Question | Page | Signal |
|---|---|---|
| What audit records exist for a partner on a given date? | Audit Logs | Table of batch windows; filterable by date |
| Did HIGH/CRITICAL batches generate theft reports for a partner? | Theft Reports | Report list per partner |
| Which users were flagged in a given theft report? | Theft Reports → detail | User Results table |
| What were the five feature values for a flagged user? | Theft Reports → detail | `query_count`, `unique_input_ratio`, `avg_input_length`, `input_entropy`, `output_diversity` |

---

## Gaps — Questions the Dashboard Cannot Answer

### 1. System-wide risk level distribution
**Question:** What is the distribution of LOW / MEDIUM / HIGH / CRITICAL batches across all partners over the last 24 hours?

The System Health page shows the risk-level score reference chart, but contains no real data. Audit Logs require a manual per-partner query; there is no cross-partner aggregate view. An operator cannot answer this question without querying every partner individually and summing by hand.

### 2. Cross-partner theft report feed
**Question:** What HIGH or CRITICAL theft reports have been filed across all partners in the last hour?

Theft Reports require the operator to type a specific partner ID. There is no "recent reports" feed that surfaces new HIGH/CRITICAL events across all partners. A campaign targeting multiple partners simultaneously would only be noticed if every partner ID is manually checked.

### 3. Request rate and DDoS signal (T-03)
**Question:** Is any endpoint currently receiving an abnormally high request volume? Are there signs of credential stuffing on `/auth/login`?

No rate or volume metrics are surfaced. The threat model (T-03) identifies flooding of `/batch/analyze` and `/auth/login` as active risks. The dashboard provides no request-count charts, throttle-hit counters, or failed-login metrics to detect this.

### 4. Batch integrity signal (T-01)
**Question:** Is there evidence that a partner is submitting falsified or anomalously structured query records?

The threat model (T-01) identifies batch data injection as the highest-impact manipulation vector. The dashboard has no indicator for batch payload anomalies such as unusually small record counts, missing fields, all-zero feature vectors, or sudden shifts in the ratio of HIGH-to-LOW results for a partner. Detection of T-01 requires out-of-band verification the system does not currently implement, but the dashboard does not even surface a warning that batch integrity is unverified.

### 5. Audit log tampering signal (T-02)
**Question:** Have any audit log objects in MinIO been modified or deleted since they were written?

The threat model (T-02) identifies mutable audit logs as a high-impact risk. MinIO object locking (WORM) is not enabled, and the dashboard has no record-count reconciliation, hash verification, or last-modified timestamp display to detect silent deletion or modification of audit records.

### 6. Detector model provenance
**Question:** When was the detector model last trained? What version is deployed?

The System Health page confirms the detector is `LOADED` but shows no model metadata — no training timestamp, training sample count, or version hash. An operator cannot tell whether the model in production matches the expected artifact.

### 7. Storage capacity
**Question:** Is any MinIO bucket approaching its storage limit?

The threat model (T-03) calls out disk exhaustion via `/batch/analyze` flooding as an active risk. The dashboard has no bucket-size or disk-usage metric. Capacity pressure is invisible until writes begin to fail.

### 8. Date-range queries on audit logs
**Question:** How many HIGH/CRITICAL batches did partner X submit between 2026-05-10 and 2026-05-14?

The Audit Logs page accepts a single date filter only. Multi-day investigation requires one manual query per day and manual aggregation by the operator.

### 9. Per-user risk trend across batch windows
**Question:** Is a specific `query_user` escalating their activity across consecutive batch windows?

A flagged user appears in a single theft report, but there is no view that tracks a user's risk score across multiple reports over time. Sustained low-and-slow extraction campaigns that stay below CRITICAL in any individual batch may go unnoticed.

### 10. Batch payload size visibility
**Question:** How many query records are in each submitted batch?

No batch record-count metric is displayed. The threat model notes the absence of a `max_records` validator, meaning a single oversized batch can exhaust resources. The dashboard gives no signal that a batch was unusually large.
