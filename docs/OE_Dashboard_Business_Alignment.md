# OE Dashboard — Business Risk Alignment

Comparison of the business impact/continuity analysis against what the OE dashboard currently surfaces.

---

## Business Questions vs. Dashboard Coverage

| Business Question | Source in Analysis | Dashboard Coverage | Gap |
|---|---|---|---|
| Is an active extraction campaign in progress right now? | False negatives are the catastrophic failure — stolen IP is irreversible | Theft Reports page (per-partner, manual lookup) | No cross-partner feed; no real-time alert; operator must poll every partner individually |
| Are legitimate users being incorrectly flagged? | False positives cause churn, service degradation, and legal exposure | None | No false-positive feedback loop; no way to distinguish "user flagged once and disputed" from confirmed theft |
| Which partners are high-stakes vs. low-stakes? | Financial firms tolerate more false positives; consumer APIs tolerate fewer | None | No customer-segment or risk-tolerance metadata is stored or displayed |
| What threshold is each partner running at? | Threshold is the lever for putting risk tolerance where it belongs — with the customer | None | Thresholds are hardcoded in detection logic; no per-partner threshold is stored, displayed, or auditable |
| Has a threshold been breached in the last hour? | Threshold breach is the primary action trigger | None | No aggregated "recent threshold events" view across partners |
| Has a flagged user been escalating across multiple batch windows? | Low-and-slow campaigns may stay below CRITICAL per-batch | Theft Reports show per-report user results | No cross-report user trend; sustained campaigns below the per-batch threshold are invisible |
| Can we prove to a disputed-classification customer what we saw and why? | False positive accusations may carry legal exposure | Theft Reports detail shows feature values for flagged users | Feature values are logged but there is no exportable, customer-facing evidence summary |
| Is the detector becoming less accurate over time? | Engineering accuracy goals must serve the business goal of catching extraction | System Health confirms detector is `LOADED` | No model performance metrics — no drift signal, no accuracy trend, no training-data comparison |
| Is "no alerts" a healthy signal or a broken detector? | A false-negative failure is silent by definition | System Health confirms detector is loaded, not that it is performing correctly | `LOADED` ≠ `ACCURATE`; there is no canary or baseline detection test to confirm liveness |

---

## Summary

The dashboard is **operationally sufficient** for confirming the system is running and retrieving historical records for a known partner. It does not yet support the business-level decisions described in the analysis.

### What the dashboard answers well
- Service liveness (are all four components up?)
- Partner submission cadence (who has gone stale?)
- Post-hoc record retrieval for a specific partner and date

### What the analysis requires that the dashboard cannot provide
- **False-negative visibility** — no way to detect a missed campaign; the system is silent on what it did not flag
- **False-positive feedback** — no mechanism to record or surface disputed classifications
- **Threshold governance** — per-partner thresholds are the core product differentiator described in the analysis; they do not exist in the current system or UI
- **Detector health beyond liveness** — `LOADED` status does not confirm the model is producing calibrated, accurate scores
