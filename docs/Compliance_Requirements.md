# Compliance Requirements

ModelGuard operates as an AI security monitoring platform: it ingests query batches, runs anomaly detection, stores audit logs, and generates theft reports. This document maps the compliance obligations most relevant to that product profile.

---

## 1. EU AI Act

**Applicability:** High — ModelGuard processes AI system outputs and produces risk scores that influence downstream decisions about users.

The EU AI Act entered into force August 1, 2024 and became fully applicable **August 2, 2026**. Systems that monitor, evaluate, or adjudicate AI behaviour may be classified as high-risk AI depending on the sector of deployment (e.g., employment, law enforcement, critical infrastructure). Even if ModelGuard is classified as a lower-risk tool, providers who deploy it on top of high-risk systems must satisfy obligations that flow down to supporting tooling.

### Key obligations

| Obligation | Requirement | ModelGuard gap today |
|---|---|---|
| **Technical documentation** | Maintain current docs describing architecture, training data, performance metrics, and known limitations | Partially covered by `Technical_Design.md`; no formal AI system card |
| **Automatic logging** | Record events sufficient to identify risks and reconstructing decisions throughout the system lifecycle | `store_audit_log` writes to MinIO, but MinIO has no WORM/object-lock (T-02) |
| **Post-market monitoring** | Continuous monitoring program; report serious incidents to authorities within strict timelines | No incident-reporting workflow exists |
| **Human oversight** | High-risk systems must allow human review of outputs before consequential action | Dashboard exists but no formal override/acknowledge flow |
| **Conformity assessment** | Self-assessment or third-party audit; CE marking; EU database registration if high-risk | Not initiated |

### Deadlines
- **Feb 2, 2025** — prohibited AI practices and AI literacy obligations apply
- **Aug 2, 2026** — full applicability for high-risk systems; conformity assessments must be complete

**Sources:**
- [EU AI Act 2026 Updates: Compliance Requirements and Business Risks](https://www.legalnodes.com/article/eu-ai-act-2026-updates-compliance-requirements-and-business-risks)
- [EU AI Act Compliance 2026 | Timeline, High-Risk AI Guide](https://www.gdprregister.eu/regulations/eu-ai-act-compliance/)
- [High-level summary of the AI Act | EU Artificial Intelligence Act](https://artificialintelligenceact.eu/high-level-summary/)
- [Implementation Timeline | EU Artificial Intelligence Act](https://artificialintelligenceact.eu/implementation-timeline/)

---

## 2. GDPR

**Applicability:** High if any EU-resident user data appears in query payloads submitted to `/batch/analyze`.

Query records submitted to ModelGuard (`input`, `output`, `query_user`) are likely to contain personal data. Under GDPR, ModelGuard acts as a **data processor** on behalf of the partner submitting data, and the partner is the **data controller**.

### Key obligations

| Obligation | Requirement | ModelGuard gap today |
|---|---|---|
| **Article 28 DPA** | A Data Processing Agreement must exist between ModelGuard and each partner | No DPA template in place |
| **Article 30 records** | Audit trail must capture: triggering request, data classification, external transmissions, legal basis, and enforcement events | Audit log stores raw results; no legal-basis or data-classification field |
| **Article 25 — data minimisation** | Collect and retain only data necessary for the detection purpose | Full query `input`/`output` text retained indefinitely; no retention policy |
| **Article 35 DPIA** | Mandatory for high-risk processing (systematic monitoring of individuals at scale) | Not performed |
| **Article 17 — right to erasure** | Partners may need to delete individual records on subject request | MinIO objects are not indexed by data-subject identity |
| **Breach notification** | 72-hour notification to supervisory authority for qualifying breaches | No breach-detection or notification workflow |

### 2026 enforcement context
On March 19, 2026, the EDPB launched a Coordinated Enforcement Action auditing organisations on their GDPR transparency and information obligations for AI-processed data.

**Sources:**
- [GDPR Compliance in 2026: The Complete Guide](https://secureprivacy.ai/blog/gdpr-compliance-2026)
- [Your AI Agents Are Processing Personal Data. GDPR Now Requires You to Prove It.](https://dev.to/waxell/your-ai-agents-are-processing-personal-data-gdpr-now-requires-you-to-prove-it-1ghd)
- [The Intersection of GDPR and AI and 6 Compliance Best Practices](https://www.exabeam.com/explainers/gdpr-compliance/the-intersection-of-gdpr-and-ai-and-6-compliance-best-practices/)

---

## 3. NIST AI Risk Management Framework (AI RMF 1.0)

**Applicability:** Voluntary but increasingly cited by regulators (FTC, SEC, Treasury) as the standard of care for AI systems.

The NIST AI RMF organises risk management into four functions:

| Function | What it means for ModelGuard |
|---|---|
| **Govern** | Establish policies, roles, and accountability for AI risk (RBAC is present; written policy is not) |
| **Map** | Identify where AI is used and what can go wrong (Threat Model covers T-01/T-02/T-03; no formal context mapping against deployment scenarios) |
| **Measure** | Quantify and track risks over time (Isolation Forest scores are computed; no historical drift or false-positive rate tracking) |
| **Manage** | Prioritise and treat identified risks (mitigations for T-01/T-02/T-03 are not yet implemented) |

NIST AI 600-1 (Generative AI Profile, 2024) adds guidance on model extraction attacks, output integrity, and transparency — directly relevant to ModelGuard's threat model.

In February 2026 the Treasury Department published a Financial Services AI RMF translating NIST principles into 230 control objectives for financial institutions. If ModelGuard is deployed in financial services, those controls become effectively mandatory.

**Sources:**
- [AI Risk Management Framework | NIST](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST AI 100-1 (AI RMF 1.0)](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf)
- [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [NIST AI RMF 2025–2026 Updates](https://www.ispartnersllc.com/blog/nist-ai-rmf-2025-2026-updates-what-you-need-to-know-about-the-latest-framework-changes/)

---

## 4. SOC 2 Type II

**Applicability:** Enterprise SaaS baseline — most enterprise customers require SOC 2 Type II for vendor qualification.

SOC 2 audits evaluate controls across five Trust Services Criteria (TSC). The most relevant for ModelGuard:

| TSC | Requirement | ModelGuard gap today |
|---|---|---|
| **Security (CC)** | Access controls, change management, security monitoring, anomaly detection | RBAC present; no change-management process for model artefacts; no WAF/rate limiting (T-03) |
| **Availability (A)** | Uptime SLAs, capacity management, incident response | No SLA defined; no auto-scaling; no incident runbook for service outages |
| **Confidentiality (C)** | Protect confidential information throughout lifecycle; least-privilege access to model artefacts | MinIO bucket policies not restricted to least-privilege; no encryption-in-transit verification |
| **Processing Integrity (PI)** | Ensure processing is complete, accurate, and authorised | T-01 (batch injection) directly violates PI; no integrity check on submitted records |

### AI-specific SOC 2 requirements (2026)
- Immutable logging of AI inputs and outputs
- Continuous monitoring for anomalous AI behaviour
- Explainability documentation for automated decisions
- Access reviews for training datasets and model artefact stores

Typical timeline: 6–12 months to Type II certification.

**Sources:**
- [SOC 2 Compliance for AI Agents in 2026](https://blaxel.ai/blog/soc-2-compliance-ai-guide)
- [SOC 2 Compliance in 2026: Requirements, Controls, and Best Practices](https://www.venn.com/learn/soc2-compliance/)
- [SOC 2 Compliance for AI Companies](https://www.eisneramper.com/insights/soc-services/soc-2-compliance-ai-companies-0426/)
- [How AI Agents Impact SOC 2 Trust Services Criteria](https://goteleport.com/blog/ai-agents-soc-2/)

---

## 5. ISO/IEC 27001:2022

**Applicability:** International baseline for information security management; often required alongside or instead of SOC 2 in non-US markets.

The 2022 revision of ISO 27001 added 11 new controls in Annex A that directly affect AI platforms. The most relevant:

| Control area | Requirement | ModelGuard gap today |
|---|---|---|
| **A.5.23 — Cloud services** | Security requirements for using cloud/SaaS (MinIO as S3-compatible store) must be defined and contractually enforced | No formal cloud security policy |
| **A.8.8 — Vulnerability management** | Timely identification and remediation of technical vulnerabilities in all systems | No CVE scanning in CI/CD |
| **A.8.16 — Monitoring activities** | Anomalous behaviour detection across all systems | Detection covers queries but not infrastructure layer |
| **A.5.30 — ICT continuity** | Backup and recovery for critical systems | No backup policy for model artefacts or audit logs |
| **Model artefact security** | Encryption at rest, granular access logs, and secure development to prevent unauthorised copying/theft of proprietary models | MinIO stores model artefacts; no object-level encryption policy documented |

ISO 27001 certification also satisfies many GDPR technical-measures obligations and is increasingly cited in EU AI Act conformity assessments.

**Sources:**
- [ISO 27001 AI Compliance – Information Security for AI Systems](https://aihealthcarecompliance.com/resources/applicable-laws/iso-27001/)
- [ISO 27001 Policies for AI Companies: A Strategic Guide](https://hightable.io/iso-27001-policies-for-ai-companies/)
- [AI-related threats and ISO 27001 compliance](https://copla.com/blog/compliance-regulations/addressing-ai-related-threats-through-iso-27001-compliance/)

---

## 6. OWASP LLM Top 10 (2025)

**Applicability:** Not a regulation, but the de-facto security checklist cited in SOC 2 readiness work and enterprise vendor questionnaires for AI platforms.

The most relevant risks for ModelGuard:

| Risk | Description | ModelGuard relevance |
|---|---|---|
| **LLM06 — Sensitive Information Disclosure** | AI outputs expose confidential data from training or context | Theft reports contain reconstructed query patterns; must be access-controlled |
| **LLM10 — Model Theft** | Adversaries extract a functionally equivalent shadow model via repeated API queries | ModelGuard's core detection target; the platform itself must also protect its own Isolation Forest artefact |
| **LLM04 — Model DoS** | Flooding inference endpoints to exhaust compute or storage | T-03 directly maps to this; no rate limiting on `/batch/analyze` |
| **LLM01 — Prompt Injection** | Malicious content in inputs manipulates model outputs | Submitted query `input` fields could contain adversarial content designed to evade the detector |

The OWASP checklist maps mitigations to SOC 2, HIPAA, and SOX controls, making it a useful bridge document between security engineering and compliance teams.

**Sources:**
- [OWASP LLM Top 10: Implementation Checklist for 2026](https://workforcenext.in/blog/owasp-llm-top-10-implementation-checklist-2026/)
- [OWASP Top 10 For LLM Applications 2025](https://www.indusface.com/learning/owasp-top-10-llm/)
- [OWASP LLM Top 10 : The 2026 Complete Guide](https://repello.ai/blog/owasp-llm-top-10-2026)

---

## 7. Cross-cutting gaps mapped to compliance obligations

The three active threats in `Threat_Model.md` each map to multiple compliance obligations:

| Threat | EU AI Act | GDPR | SOC 2 | ISO 27001 | OWASP LLM |
|---|---|---|---|---|---|
| **T-01** Batch injection | Art. 9 (risk management), Art. 12 (logging) | Art. 5(1)(d) accuracy | PI1 (processing integrity) | A.8.16 monitoring | LLM01 prompt injection |
| **T-02** Mutable audit logs | Art. 12 (record-keeping) | Art. 5(1)(f) integrity & confidentiality | CC7 (monitoring), A1 (availability) | A.5.30 continuity, A.8.8 vuln management | LLM06 info disclosure |
| **T-03** No rate limiting | Art. 9 (risk management) | Art. 32 technical measures | CC6 (logical access), A1 (availability) | A.8.16 monitoring | LLM04 model DoS |

Mitigating all three threats simultaneously advances compliance posture across every framework listed in this document.
