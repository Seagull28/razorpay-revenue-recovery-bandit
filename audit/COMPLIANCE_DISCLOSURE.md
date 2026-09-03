# 🛡️ RECOVERFLOW REGULATORY & COMPLIANCE DISCLOSURE

> **Scope Boundary & Regulatory Context Disclosure for Payment Retry Scheduling in India**

---

## 1. Operating Context & Regulatory Environment

RecoverFlow is an intelligent retry scheduling engine designed to select optimal retry delays for failed digital payment transactions. In a live production deployment within the Indian payment ecosystem, automated retry mechanisms interact directly with payment system regulations governed by the **Reserve Bank of India (RBI)** and the **National Payments Corporation of India (NPCI)**.

Specifically, recurring transactions—such as **UPI AutoPay**, **e-Mandates on Credit/Debit Cards**, and **NACH (National Automated Clearing House)**—are subject to strict regulatory frameworks designed to protect consumers, ensure explicit user consent, and prevent excessive or unauthorized account debits. Key regulatory constraint categories include:

- **Retry Attempt Limits**: Strict ceilings on the maximum number of automated retry attempts permitted per failed recurring payment instruction.
- **Mandate Retry Windows**: Mandatory time intervals, cooling-off periods, and pre-debit notification windows before an automated retry attempt can be initiated against a customer's account.
- **Card-Not-Present (CNP) & Additional Factor of Authentication (AFA)**: Rules governing single-click retries vs. transactions requiring customer-initiated AFA re-authentication.

---

## 2. System Scope Boundaries & Parameter Mapping

To maintain a clean separation between algorithmic optimization and ecosystem-specific compliance rules, RecoverFlow models regulatory constraints as configurable system parameters:

- **Max Attempts Stand-In**: RecoverFlow enforces a `max_attempts` constraint (configured in policy engines such as `policies/linucb.py` and evaluation benchmarks such as `evaluation/oracle.py`, defaulted to 4 attempts). This parameter serves as a configurable stand-in for regulatory attempt ceilings.
- **Retry Window Modeling Scope**: The current synthetic evaluation benchmark (`simulator/ground_truth.py`) evaluates mathematical retry timing dynamics (`1hr`, `6hr`, `1d`, `3d`, `7d`), but does **not** simulate mandate-specific notification or cooling-off windows required by NPCI/RBI guidelines for recurring payments.
- **Ecosystem Agnosticism**: RecoverFlow operates as a decision engine receiving context vectors and returning recommended retry delays. Adapting the system to specific payment rails (e.g., UPI AutoPay vs. credit card retries) requires wrapping the decision engine in rail-specific compliance filters.

---

## 3. Summary of Constraint Categories & Prototype Scope

| Regulatory Constraint Category | Production Requirement in India | RecoverFlow Prototype Scope |
| :--- | :--- | :--- |
| **Retry Attempt Ceiling** | Capped per mandate cycle by RBI/NPCI rules | Enforced via configurable `max_attempts` parameter |
| **Execution Window Constraints** | Mandatory cooling-off & pre-notification windows | Modeled as discrete delay arms (`1hr` to `7d`); window rules out of scope |
| **Consumer Consent & AFA** | Explicit mandate registration & AFA required | Assumed pre-authorized recurring or merchant-initiated retry context |
| **Rail-Specific Rules** | Distinct rules for UPI AutoPay, NACH, and Card Mandates | Rail-agnostic decision engine; rail rules handled at integration layer |

---

## 4. Formal Compliance & Non-Certification Statement

> [!IMPORTANT]
> **Prototype Non-Certification Disclaimer**
> RecoverFlow is an experimental research prototype and technical demonstration. It is **NOT** RBI-compliant, **NOT** PCI-DSS certified, **NOT** NPCI-certified, and makes **NO** claims of regulatory certification or legal compliance. This document is provided solely to demonstrate architectural awareness of the regulatory environment governing payment retry automation in India. Production deployment requires integration with certified payment gateway infrastructure, legal review, and strict adherence to rail-specific NPCI and RBI circulars.
