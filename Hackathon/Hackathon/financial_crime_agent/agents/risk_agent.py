"""Risk Assessment Agent — weighted scoring with AML typology awareness."""
from core.models import InvestigationContext, RiskLevel


# ── Scoring weights per signal type ──────────────────────────────────────────
SIGNAL_WEIGHTS = {
    "amount_spike":          0.18,
    "geo_anomaly":           0.12,
    "structuring":           0.22,   # Classic AML red flag
    "kyc_incomplete":        0.14,
    "pep_flag":              0.14,
    "new_account_large_txn": 0.10,
    "ml_anomaly":            0.18,
    "high_risk_occupation":  0.10,
    "high_risk_merchant":    0.10,
}

# ── Enrichment boosters ───────────────────────────────────────────────────────
def _enrichment_boost(ctx: InvestigationContext) -> float:
    boost = 0.0
    enrich = ctx.enrichment_data

    if enrich.get("sanctions", {}).get("is_sanctioned"):
        boost += 0.40   # Hard boost — sanctions = near-certain escalation

    velocity = enrich.get("velocity", {})
    if velocity.get("txn_count_24h", 0) > 20:
        boost += 0.15
    if velocity.get("unique_countries_7d", 0) > 5:
        boost += 0.10

    if enrich.get("adverse_news"):
        boost += 0.10

    if enrich.get("network_risk", {}).get("network_risk"):
        boost += 0.20

    return min(boost, 0.60)   # Cap enrichment contribution


def _signal_score(ctx: InvestigationContext) -> float:
    if not ctx.signals:
        return 0.0
    score = 0.0
    for signal in ctx.signals:
        weight = SIGNAL_WEIGHTS.get(signal.signal_type, 0.10)
        score += signal.severity * weight
    return min(score, 1.0)


def _to_risk_level(score: float) -> RiskLevel:
    if score >= 0.75:
        return RiskLevel.CRITICAL
    if score >= 0.50:
        return RiskLevel.HIGH
    if score >= 0.25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _confidence(ctx: InvestigationContext) -> float:
    """Higher confidence when more evidence sources agree."""
    signal_count = len(ctx.signals)
    enrich_count = len(ctx.enrichment_data)
    # Boost confidence when signals and enrichment corroborate each other
    corroboration = 0.05 if (signal_count > 0 and enrich_count > 0) else 0.0
    return min(0.97, 0.45 + signal_count * 0.05 + enrich_count * 0.03 + corroboration)


# ── Agent entry point ─────────────────────────────────────────────────────────

class RiskAssessmentAgent:
    NAME = "RiskAssessmentAgent"

    def run(self, ctx: InvestigationContext) -> InvestigationContext:
        ctx.log(self.NAME, "Calculating risk score")

        signal_score = _signal_score(ctx)
        boost = _enrichment_boost(ctx)
        ctx.risk_score = round(min(1.0, signal_score + boost), 3)
        ctx.risk_level = _to_risk_level(ctx.risk_score)
        ctx.confidence = _confidence(ctx)

        ctx.log(self.NAME, "Risk assessment complete", {
            "signal_score": signal_score,
            "enrichment_boost": boost,
            "final_score": ctx.risk_score,
            "risk_level": ctx.risk_level,
            "confidence": ctx.confidence,
        })
        return ctx
