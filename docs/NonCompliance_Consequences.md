# Non-Compliance Consequences

This document covers the potential consequences if ModelGuard — or a customer deploying it — fails to meet the compliance obligations identified in `Compliance_Requirements.md`. Consequences are grouped by framework, then by category (regulatory, financial, contractual, reputational, operational).

---

## 1. EU AI Act

Full applicability for high-risk AI systems begins **August 2, 2026**. The Act uses a three-tier penalty structure. Where ModelGuard (or a system it monitors) is classified as high-risk, the fines below apply directly to the provider.

### Fine tiers

| Violation tier | Maximum fine |
|---|---|
| **Prohibited AI practice** (e.g., social scoring, subliminal manipulation) | €35 million or **7% of global annual turnover**, whichever is higher |
| **High-risk AI system requirements** (risk management, logging, technical documentation, human oversight, cybersecurity) | €15 million or **3% of global annual turnover**, whichever is higher |
| **Providing incorrect or misleading information** to authorities | €7.5 million or **1% of global annual turnover**, whichever is higher |

### Enforcement mechanism
National competent authorities carry out investigations and impose fines. The European AI Office coordinates cross-border enforcement and can demand documentation, conduct evaluations, and require source-code access. As of April 2026, prohibited-practice rules and GPAI model rules are already enforceable; high-risk obligations take full effect in August 2026.

### Direct exposure for ModelGuard
- **T-02 (mutable audit logs)** — the absence of immutable logging is a violation of Article 12 (automatic record-keeping for high-risk systems). A market surveillance authority finding this gap could treat it as a Tier 2 breach.
- **T-01 (batch injection)** — if falsified logs reach regulators or auditors, submitting incorrect information could trigger Tier 3 fines, with potential escalation if it is deemed deliberate.
- **Missing technical documentation** — Article 11 requires current documentation; an authority requesting it and finding it absent triggers Tier 3 immediately.

**Sources:**
- [Article 99: Penalties | EU Artificial Intelligence Act](https://artificialintelligenceact.eu/article/99/)
- [EU AI Act Penalties Explained: Avoid Costly Non-Compliance](https://aqua-cloud.io/eu-ai-act-penalties-non-compliance/)
- [EU AI Act Fines and Penalties: What You Risk for Non-Compliance 2026](https://actproof.ai/blog/eu-ai-act-fines-penalties-compliance)
- [EU AI Act 2026: Requirements, Fines & Compliance Guide](https://www.compliquest.com/en/blog/what-is-eu-ai-act-requirements-2026)

---

## 2. GDPR

GDPR enforcement is active and growing. Cumulative fines across all EU member states exceeded **€7.1 billion** through early 2026, with 2025 alone contributing approximately €1.2 billion. The March 2026 EDPB Coordinated Enforcement Action specifically targeted AI data-processing transparency — the exact processing ModelGuard performs on query batches.

### Fine tiers

| Violation category | Maximum fine |
|---|---|
| **Most serious** — unlawful processing, no legal basis, transfer violations (Articles 5, 6, 9, 44) | €20 million or **4% of global annual turnover**, whichever is higher |
| **Less serious** — documentation failures, missing DPA, breach notification delays (Articles 13–14, 28, 33) | €10 million or **2% of global annual turnover**, whichever is higher |

### Recent enforcement precedents
- **TikTok** — €530 million (Irish DPC, May 2025) for unlawful EU-to-China data transfers
- **Google** — €325 million (CNIL, September 2025) for ad-tech and consent violations
- **Clearview AI** — €30.5 million (Dutch DPA) plus a ban on processing Dutch citizens' data
- **Meta** — €405 million (2022) for children's data mishandling on Instagram; the scale shows fines apply to ancillary processing, not only core products

### Direct exposure for ModelGuard
- **No Data Processing Agreement** — operating as a data processor without a signed DPA is a direct Article 28 violation (Tier 2 fine).
- **No retention policy** — indefinite storage of full query `input`/`output` text violates Article 5(1)(e) storage limitation (Tier 1 fine risk).
- **No DPIA** — systematic monitoring of individuals at scale without a prior Data Protection Impact Assessment violates Article 35 (Tier 2).
- **Breach notification gap** — failure to notify the relevant supervisory authority within 72 hours of becoming aware of a qualifying breach is a Tier 2 violation; average breach cost in 2025 exceeded **$4.5 million** before fines.
- **Right to erasure** — inability to locate and delete a data subject's records on request violates Article 17 (Tier 1 fine risk).

**Sources:**
- [GDPR Enforcement and Fines 2026: Business Categories, Top Cases, and Country](https://www.uniconsent.com/blog/gdpr-enforcement-fines-2026)
- [GDPR Fines Hit €7.1 Billion: Data Privacy Enforcement Trends in 2026](https://www.kiteworks.com/gdpr-compliance/gdpr-fines-data-privacy-enforcement-2026/)
- [Biggest GDPR fines of 2025](https://complydog.com/blog/biggest-gdpr-fines-of-2025)
- [Fines for GDPR violations in AI systems and how to avoid them](https://data-privacy-office.eu/fines-for-gdpr-violations-in-ai-systems-and-how-to-avoid-them/)

---

## 3. SOC 2 Type II

SOC 2 carries no regulatory fine. Its consequence is commercial: the absence of a SOC 2 Type II report directly blocks enterprise sales.

### Market data
- **83%** of enterprise buyers require SOC 2 Type II before signing a contract; among companies with more than 5,000 employees, that rises to **91%** (Vanta State of Trust Report, 2025).
- **67%** of startups that obtained SOC 2 said it directly enabled deals they would otherwise have lost, with a median deal size of **$120,000**.
- A documented case study shows a B2B SaaS company lost a **$380,000 annual contract** — after seven months of sales cultivation — when the prospect's security team discovered the absence of a SOC 2 report six weeks before signing.

### Direct exposure for ModelGuard
- **T-01 (batch injection)** violates SOC 2's Processing Integrity (PI1) criterion. An auditor finding no integrity check on submitted query records would issue a qualified opinion, which is functionally equivalent to no certification for enterprise procurement purposes.
- **T-02 (mutable audit logs)** violates the Availability (A1) and Security (CC7) criteria, which require immutable evidence trails.
- **T-03 (no rate limiting)** violates the Availability criterion's capacity management controls.
- A qualified or failed audit also generates findings that must be disclosed in the SOC 2 report itself — visible to every prospective customer who requests it.

**Sources:**
- [SOC 2 Compliance in 2026: Requirements, Controls, and Best Practices](https://www.venn.com/learn/soc2-compliance/)
- [SOC 2 Compliance for AI Companies](https://www.eisneramper.com/insights/soc-services/soc-2-compliance-ai-companies-0426/)
- [SOC 2 for Enterprises: Implementation Steps and Key Challenges](https://sprinto.com/blog/soc-2-for-enterprise/)
- [Maintaining SOC 2 Compliance in 2026](https://scytale.ai/resources/maintaining-soc-2-compliance/)

---

## 4. ISO/IEC 27001:2022

Like SOC 2, ISO 27001 non-compliance does not carry direct regulatory fines — its consequences are certification loss, contract loss, and increased exposure in regulatory proceedings.

### Consequences of non-certification or lapsed certification
- A single **major nonconformity** found during audit will prevent initial certification or cause suspension of an existing certificate until remediated.
- Losing or failing to achieve ISO 27001 certification slows enterprise sales cycles in non-US markets (particularly EMEA and APAC, where ISO 27001 is often preferred over SOC 2).
- ISO 27001 certification is increasingly cited as evidence of technical measures under GDPR Article 32. Without it, organizations bear a heavier burden of proof in regulatory investigations.
- Following a breach, absence of ISO 27001 certification is routinely used by plaintiffs' counsel to argue a failure to meet the industry standard of care, increasing litigation exposure.

### Documented breach-cost patterns
Companies that ignored ISO 27001 business continuity controls suffered extended operational downtime and financial losses in the studied cases. The average cost of a data breach in 2025 exceeded **$4.5 million**; standard SaaS liability caps (typically 12 months of fees) cover less than 3% of that exposure, leaving customers — and potentially ModelGuard — exposed to indemnity claims.

**Sources:**
- [Consequences of Non-compliance: Fines, Risks & Real Examples](https://sprinto.com/blog/consequences-of-non-compliance/)
- [ISO 27001 AI Compliance – Information Security for AI Systems](https://aihealthcarecompliance.com/resources/applicable-laws/iso-27001/)
- [10 Terrifying Examples of Companies Ignoring ISO 27001 Business Continuity Policies](https://secureslate.medium.com/10-terrifying-examples-of-companies-ignoring-iso-27001-business-continuity-policies-2fc8d12dab3e)
- [SaaS Security Risks 2026: Misconfigurations, Compliance Gaps, and Data Breach Prevention](https://redsentry.com/resources/blog/saas-security-risks-2026-misconfigurations-compliance-gaps-and-data-breach-prevention)

---

## 5. AI model theft — IP and legal liability

ModelGuard's core purpose is to detect model theft. If it fails to detect an extraction attack, or if its own model artefact (the Isolation Forest detector) is stolen, the following consequences apply.

### Consequences of undetected model theft (product failure)
- A customer whose model is extracted via repeated API queries — which ModelGuard missed — faces **loss of proprietary IP** built on potentially millions of dollars of training compute and data acquisition.
- Victims can pursue: actual damages, disgorgement of infringer profits, statutory damages, and treble damages for wilful infringement. The **$1.5 billion Bartz v. Anthropic settlement** (2025) established that courts will hold AI companies to very large statutory damage calculations when IP is misappropriated at scale.
- US artificial intelligence developers have accused Chinese firms of data and model theft in active litigation (2025–2026), raising the strategic stakes beyond civil damages to national-security classification in some sectors.

### Consequences of ModelGuard's own model artefact being stolen
- The Isolation Forest model stored in MinIO (`modelguard-detectors` bucket) is ModelGuard's proprietary IP. If an attacker reads or copies it (possible today given the absence of object-level access controls), the detection logic is exposed — both as a business loss and as intelligence enabling evasion of the detector.
- OWASP LLM10 (model theft) treats this as a first-class IP risk: an attacker who extracts a functionally equivalent shadow model undermines the entire value proposition of the product.

**Sources:**
- [AI Model Theft: Risks and Prevention](https://www.nextlabs.com/intelligent-enterprise/data-security-for-ai/preventing-ai-model-theft/)
- [The 10 Most Consequential Legal Rulings on AI in 2025-2026](https://globallawlists.org/insights/the-10-most-consequential-legal-rulings-on-ai-in-2025-2026-what-every-lawyer-must-know/)
- [OWASP LLM Top 10 : The 2026 Complete Guide](https://repello.ai/blog/owasp-llm-top-10-2026)
- [US artificial intelligence developers accuse Chinese firms of stealing their data](https://www.computerweekly.com/news/366639367/US-artificial-intelligence-developers-accuse-Chinese-firms-of-stealing-their-data)

---

## 6. Consequences mapped to active threats

The three threats in `Threat_Model.md` each carry distinct non-compliance consequences:

| Threat | Regulatory consequence | Commercial consequence | Operational consequence |
|---|---|---|---|
| **T-01** Batch data injection | EU AI Act Tier 2–3 fine (false records); GDPR Art. 5(1)(d) accuracy violation | SOC 2 PI1 disqualifier; failed vendor questionnaire | Falsified theft reports; incorrect risk scores reaching customers |
| **T-02** Mutable audit logs | EU AI Act Art. 12 violation (Tier 2); GDPR Art. 5(1)(f) integrity violation | SOC 2 CC7/A1 finding; ISO 27001 A.5.30 nonconformity | Audit evidence inadmissible in legal proceedings; inability to reconstruct incidents |
| **T-03** No rate limiting | EU AI Act Art. 9 risk-management gap; GDPR Art. 32 technical-measures gap | SOC 2 A1 (availability) finding | Storage exhaustion; `/batch/analyze` and `/auth/login` denial-of-service; brute-force credential attacks |

Mitigating all three simultaneously closes the most acute regulatory, commercial, and operational risk vectors in a single remediation cycle.
