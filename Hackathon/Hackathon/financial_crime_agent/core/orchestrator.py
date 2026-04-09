"""
Orchestrator — coordinates the multi-agent investigation pipeline.
Supports both single-transaction and batch processing.
"""
from core.models import InvestigationContext, Transaction, CustomerProfile
from agents.anomaly_agent import AnomalyDetectionAgent
from agents.enrichment_agent import DataEnrichmentAgent
from agents.risk_agent import RiskAssessmentAgent
from agents.explanation_agent import ExplanationAgent
from agents.decision_agent import DecisionAgent
import json


class InvestigationOrchestrator:
    """
    Pipeline: Anomaly → Enrichment → Risk → Explanation → Decision

    Short-circuit: skip enrichment + downstream if no signals detected
    (reduces cost and latency for clean transactions).
    """

    def __init__(self):
        self._agents = [
            AnomalyDetectionAgent(),
            DataEnrichmentAgent(),
            RiskAssessmentAgent(),
            ExplanationAgent(),
            DecisionAgent(),
        ]

    def investigate(self, transaction: Transaction, customer: CustomerProfile) -> InvestigationContext:
        ctx = InvestigationContext(transaction=transaction, customer=customer)
        ctx.log("Orchestrator", "Investigation started", {"transaction_id": transaction.transaction_id})

        for agent in self._agents:
            ctx = agent.run(ctx)

            # Early exit: no signals after anomaly detection → skip remaining agents
            if agent.NAME == "AnomalyDetectionAgent" and not ctx.signals:
                ctx.log("Orchestrator", "No signals detected — fast-path exit")
                break

        ctx.log("Orchestrator", "Investigation complete", {
            "action": ctx.recommended_action,
            "risk_score": ctx.risk_score,
        })
        return ctx

    def to_report(self, ctx: InvestigationContext) -> dict:
        """Serialize investigation result to audit-ready JSON."""
        return {
            "case_id": ctx.case_id,
            "transaction_id": ctx.transaction.transaction_id,
            "account_id": ctx.transaction.account_id,
            "fraud_risk_score": ctx.risk_score,
            "risk_level": ctx.risk_level,
            "confidence": ctx.confidence,
            "recommended_action": ctx.recommended_action,
            "explanation": ctx.explanation,
            "signals": [
                {"type": s.signal_type, "severity": s.severity, "description": s.description}
                for s in ctx.signals
            ],
            "audit_trail": ctx.audit_trail,
            "created_at": ctx.created_at.isoformat(),
        }
