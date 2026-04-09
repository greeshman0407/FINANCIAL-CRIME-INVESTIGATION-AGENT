"""Explanation Generation Agent — detailed structured AI narrative."""
from core.models import InvestigationContext, RiskLevel
from datetime import datetime

_RISK_INTROS = {
    RiskLevel.CRITICAL: "CRITICAL RISK — Immediate intervention required. Multiple high-severity indicators confirm strong likelihood of financial crime.",
    RiskLevel.HIGH:     "HIGH RISK — Strong indicators of financial crime detected. Escalation and manual review are strongly recommended.",
    RiskLevel.MEDIUM:   "MEDIUM RISK — Suspicious patterns identified. Transaction warrants closer investigation before processing.",
    RiskLevel.LOW:      "LOW RISK — Minor anomalies noted. No immediate action required; routine monitoring advised.",
}

_SIGNAL_TEMPLATES = {
    "amount_spike":          "Transaction amount is {ratio:.1f}x above the customer's daily average, indicating an unusual spike inconsistent with historical behaviour.",
    "geo_anomaly":           "Transaction originated in {txn_country} while the customer resides in {residence}. Cross-border activity in this corridor is flagged as elevated risk.",
    "structuring":           "Amount ${amount:.2f} falls just below the ${threshold} reporting threshold — a classic structuring (smurfing) pattern used to evade CTR filing obligations.",
    "kyc_incomplete":        "Customer KYC status is '{kyc_status}'. Unverified identity significantly increases the risk of fraudulent or illicit activity.",
    "pep_flag":              "Customer is classified as a Politically Exposed Person (PEP). PEPs carry elevated money laundering risk due to potential abuse of public office.",
    "new_account_large_txn": "Account is only {account_age_days} days old yet processed a high-value transaction of ${amount:.2f}. New accounts with large transactions are a common fraud vector.",
    "ml_anomaly":            "The ML anomaly model assigned a score of {ml_score:.2f}/1.0, indicating this transaction deviates significantly from normal behavioural patterns.",
    "high_risk_occupation":  "Customer occupation '{occupation}' is categorised as high-risk under AML typologies. Enhanced due diligence is required.",
    "high_risk_merchant":    "Transaction via '{merchant_category}' — a high-risk merchant category frequently associated with money laundering and fraud.",
}

_ACTION_GUIDANCE = {
    "BLOCK":    "RECOMMENDED ACTION: BLOCK — Immediately freeze the transaction and account. File a Suspicious Activity Report (SAR) with the relevant FIU. Do not tip off the customer.",
    "ESCALATE": "RECOMMENDED ACTION: ESCALATE — Refer to the AML compliance team for Level 2 review. Gather additional documentation. Consider filing a SAR.",
    "MONITOR":  "RECOMMENDED ACTION: MONITOR — Flag account for enhanced monitoring. Review next 30 days of activity. No immediate action required.",
    "PASS":     "RECOMMENDED ACTION: PASS — Transaction appears legitimate. No further action required at this time.",
}

_TYPOLOGY_MAP = {
    "structuring":           "AML Typology: Structuring / Smurfing (FATF Ref: TF-01)",
    "pep_flag":              "AML Typology: Politically Exposed Person Risk (FATF Ref: R.12)",
    "geo_anomaly":           "AML Typology: Geographic Risk / Sanctions Corridor",
    "amount_spike":          "AML Typology: Unusual Transaction Pattern (FATF Ref: R.20)",
    "kyc_incomplete":        "AML Typology: Identity Risk / CDD Failure (FATF Ref: R.10)",
    "new_account_large_txn": "AML Typology: Mule Account / Account Takeover Risk",
    "ml_anomaly":            "AML Typology: Behavioural Anomaly (ML-Detected)",
    "high_risk_occupation":  "AML Typology: High-Risk Customer Category (FATF Ref: R.12)",
    "high_risk_merchant":    "AML Typology: High-Risk Business Sector (FATF Ref: R.22)",
}


def _build_signal_section(ctx: InvestigationContext) -> str:
    if not ctx.signals:
        return "  No rule-based signals triggered.\n"
    lines = []
    for i, s in enumerate(ctx.signals, 1):
        template = _SIGNAL_TEMPLATES.get(s.signal_type, s.description)
        try:
            detail = template.format(**s.evidence)
        except KeyError:
            detail = s.description
        severity_label = "CRITICAL" if s.severity >= 0.8 else "HIGH" if s.severity >= 0.6 else "MEDIUM" if s.severity >= 0.4 else "LOW"
        typology = _TYPOLOGY_MAP.get(s.signal_type, "")
        lines.append(
            f"  [{i}] {s.signal_type.upper().replace('_',' ')} (Severity: {s.severity:.0%} — {severity_label})\n"
            f"      {detail}\n"
            + (f"      {typology}\n" if typology else "")
        )
    return "\n".join(lines)


def _build_enrichment_section(ctx: InvestigationContext) -> str:
    lines = []
    enrich = ctx.enrichment_data

    sanctions = enrich.get("sanctions", {})
    if sanctions.get("is_sanctioned"):
        for hit in sanctions.get("sanctions_hits", []):
            lines.append(f"  ⚠ SANCTIONS HIT — Entity '{hit.get('name')}' matched on {hit.get('list')} ({hit.get('program')}). This is a hard block trigger.")
    else:
        lines.append("  ✓ Sanctions Check — No matches found on OFAC SDN list.")

    velocity = enrich.get("velocity", {})
    txn_24h = velocity.get("txn_count_24h", 0)
    countries_7d = velocity.get("unique_countries_7d", 1)
    if txn_24h > 20:
        lines.append(f"  ⚠ HIGH VELOCITY — {txn_24h} transactions in last 24h across {countries_7d} countries. Indicative of layering or account compromise.")
    elif txn_24h > 10:
        lines.append(f"  ⚡ ELEVATED VELOCITY — {txn_24h} transactions in last 24h. Monitor for further escalation.")
    else:
        lines.append(f"  ✓ Velocity Check — Normal activity ({txn_24h} txns/24h).")

    for news in enrich.get("adverse_news", []):
        lines.append(f"  ⚠ ADVERSE NEWS — {news}")

    network = enrich.get("network_risk", {})
    if network.get("network_risk"):
        lines.append(f"  ⚠ NETWORK RISK — {network['reason']}")
    else:
        lines.append("  ✓ Network Check — No known high-risk counterparty links.")

    return "\n".join(lines)


def _build_explanation(ctx: InvestigationContext) -> str:
    txn = ctx.transaction
    cust = ctx.customer
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    intro        = _RISK_INTROS[ctx.risk_level]
    signals_sec  = _build_signal_section(ctx)
    enrich_sec   = _build_enrichment_section(ctx)
    action_guide = _ACTION_GUIDANCE.get(ctx.recommended_action.value if hasattr(ctx.recommended_action, 'value') else str(ctx.recommended_action), "")

    sar_note = ""
    if ctx.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        sar_note = "\n[REGULATORY] Suspicious Activity Report (SAR) filing is recommended under FinCEN/FIU guidelines.\n"

    return f"""{'='*70}
FINGUARD FINANCIAL CRIME INVESTIGATION REPORT
{'='*70}
Generated : {now}
Case ID   : {ctx.case_id}
Risk Score: {ctx.risk_score:.3f} / 1.000
Risk Level: {ctx.risk_level.value}
Confidence: {ctx.confidence:.0%}
{'='*70}

EXECUTIVE SUMMARY
{'-'*70}
{intro}

TRANSACTION DETAILS
{'-'*70}
  Transaction ID : {txn.transaction_id}
  Account ID     : {txn.account_id}
  Amount         : ${txn.amount:,.2f} {txn.currency}
  Country        : {txn.country}
  Channel        : {txn.channel}
  Merchant Cat.  : {txn.merchant_category}
  Counterparty   : {txn.counterparty_id or 'N/A'}

CUSTOMER PROFILE
{'-'*70}
  Name           : {cust.name}
  Residence      : {cust.country_of_residence}
  KYC Status     : {cust.kyc_status.upper()}
  Account Age    : {cust.account_age_days} days
  Avg Monthly Txn: ${cust.avg_monthly_txn_amount:,.0f}
  Occupation     : {cust.occupation}
  PEP Flag       : {'YES — Enhanced Due Diligence Required' if cust.pep_flag else 'No'}
  Sanctions Hit  : {'YES — IMMEDIATE BLOCK REQUIRED' if cust.sanctions_hit else 'No'}

DETECTED SIGNALS ({len(ctx.signals)} total)
{'-'*70}
{signals_sec}
CONTEXTUAL INTELLIGENCE
{'-'*70}
{enrich_sec}

RISK SCORING BREAKDOWN
{'-'*70}
  Signal Score      : {ctx.risk_score:.3f}
  Enrichment Boost  : Applied
  Final Risk Score  : {ctx.risk_score:.3f} → {ctx.risk_level.value}
  Model Confidence  : {ctx.confidence:.0%}
{sar_note}
COMPLIANCE GUIDANCE
{'-'*70}
{action_guide}

{'='*70}
This report was generated by FinGuard Multi-Agent AML System.
For compliance queries contact your AML Officer.
{'='*70}"""


class ExplanationAgent:
    NAME = "ExplanationAgent"

    def run(self, ctx: InvestigationContext) -> InvestigationContext:
        ctx.log(self.NAME, "Generating detailed explanation")
        ctx.explanation = _build_explanation(ctx)
        ctx.log(self.NAME, "Explanation generated")
        return ctx
