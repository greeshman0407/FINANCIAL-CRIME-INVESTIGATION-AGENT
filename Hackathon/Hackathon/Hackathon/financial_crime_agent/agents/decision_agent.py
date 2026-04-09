"""Decision Agent -- maps risk to action with false-positive reduction."""
from core.models import Action, InvestigationContext, RiskLevel


# -- False-positive reduction rules -------------------------------------------

def _is_likely_false_positive(ctx: InvestigationContext) -> bool:
    """
    Reduce false positives by checking trusted customer signals.
    Returns True if the case should be downgraded.
    """
    profile = ctx.customer
    txn = ctx.transaction

    # Long-standing verified customer with no sanctions/PEP
    if (profile.account_age_days > 730
            and profile.kyc_status == "verified"
            and not profile.pep_flag
            and not profile.sanctions_hit
            and ctx.risk_level == RiskLevel.MEDIUM):
        return True

    # Only signal is geo anomaly and amount is small
    signal_types = {s.signal_type for s in ctx.signals}
    if signal_types == {"geo_anomaly"} and txn.amount < 200:
        return True

    return False


# -- Action decision table -----------------------------------------------------

def _decide_action(ctx: InvestigationContext) -> Action:
    if ctx.customer.sanctions_hit:
        return Action.BLOCK   # Hard rule -- sanctions always block

    if _is_likely_false_positive(ctx):
        ctx.log("DecisionAgent", "False-positive reduction applied -- downgrading action")
        return Action.MONITOR

    return {
        RiskLevel.CRITICAL: Action.BLOCK,
        RiskLevel.HIGH:     Action.ESCALATE,
        RiskLevel.MEDIUM:   Action.MONITOR,
        RiskLevel.LOW:      Action.PASS,
    }[ctx.risk_level]


# -- Regulatory reporting check -----------------------------------------------

def _requires_sar(ctx: InvestigationContext) -> bool:
    """Suspicious Activity Report required for HIGH/CRITICAL cases."""
    return ctx.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


# -- Agent entry point --------------------------------------------------------

class DecisionAgent:
    NAME = "DecisionAgent"

    def run(self, ctx: InvestigationContext) -> InvestigationContext:
        ctx.log(self.NAME, "Making action decision")

        ctx.recommended_action = _decide_action(ctx)
        sar_required = _requires_sar(ctx)

        ctx.log(self.NAME, "Decision complete", {
            "action": ctx.recommended_action,
            "sar_required": sar_required,
            "risk_level": ctx.risk_level,
        })

        if sar_required:
            ctx.explanation += "\n\n[REGULATORY] Suspicious Activity Report (SAR) filing recommended."

        return ctx
