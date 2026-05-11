# Customer Disruption Risk Register: ModelGuard AI

- Version: 0.3.0-oss
- Last Updated: 2026-05-10

---

## Risk 1 — False Negatives Causing Undetected IP Theft

An ML model security product that misclassifies a real extraction campaign as normal traffic (a false negative) gives the customer a false sense of protection. The underlying model — which may cost millions of dollars and months of training — gets reconstructed by a competitor or adversary with no warning. The business impact is permanent: stolen IP cannot be un-stolen, and the customer is likely to churn and publicly blame the security vendor. This maps to a direct revenue and reputational loss for vendors in this space.

---

## Risk 2 — False Positives Causing Business Disruption and Legal Liability

A detection system that triggers HIGH/CRITICAL alerts against legitimate users can cause customers to throttle or ban paying end-users based on inaccurate signals. This creates two downstream problems: customer churn from service degradation, and potential legal liability if flagged users dispute the accusation.

---

## Risk 3 — Silent Integration Failure Leaving Customers Unprotected

A partner's integration can silently stop submitting batches — due to an API key rotation that was never propagated, a network policy change, or a misconfigured deployment — with no error visible to either party. The customer continues to believe their model is being monitored; ModelGuard continues to report no alerts. The gap in coverage may span days or weeks before it is discovered, during which a real extraction campaign would go completely undetected. This risk is not mitigated by the health check, which only monitors ModelGuard's own services and cannot observe whether a partner is submitting data. Operators can track it via the **Audit Logs** page on the OE dashboard: a previously active partner with no records for the current date is a reliable signal of a broken integration.
