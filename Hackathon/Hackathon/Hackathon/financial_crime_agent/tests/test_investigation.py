"""Tests covering key investigation scenarios."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from core.models import Transaction, CustomerProfile, Action, RiskLevel
from core.orchestrator import InvestigationOrchestrator

orchestrator = InvestigationOrchestrator()


def make_txn(**kwargs) -> Transaction:
    defaults = dict(
        transaction_id="TXN_TEST",
        account_id="ACC_001",
        amount=100.0,
        currency="USD",
        country="US",
        merchant_category="retail",
        timestamp=datetime.now(timezone.utc),
    )
    return Transaction(**{**defaults, **kwargs})


def make_customer(**kwargs) -> CustomerProfile:
    defaults = dict(
        account_id="ACC_001",
        name="Jane Doe",
        country_of_residence="US",
        kyc_status="verified",
        account_age_days=500,
        avg_monthly_txn_amount=3000.0,
        occupation="engineer",
    )
    return CustomerProfile(**{**defaults, **kwargs})


# -- Test cases ---------------------------------------------------------------

def test_clean_transaction():
    ctx = orchestrator.investigate(make_txn(amount=50.0), make_customer())
    assert ctx.recommended_action == Action.PASS
    assert ctx.risk_score < 0.25
    print("PASS test_clean_transaction")


def test_structuring_detection():
    ctx = orchestrator.investigate(make_txn(amount=9500.0), make_customer())
    signal_types = {s.signal_type for s in ctx.signals}
    assert "structuring" in signal_types
    assert ctx.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
    print("PASS test_structuring_detection")


def test_high_risk_geo():
    ctx = orchestrator.investigate(make_txn(amount=5000.0, country="IR"), make_customer())
    signal_types = {s.signal_type for s in ctx.signals}
    assert "geo_anomaly" in signal_types
    print("PASS test_high_risk_geo")


def test_pep_customer():
    ctx = orchestrator.investigate(
        make_txn(amount=50000.0),
        make_customer(pep_flag=True, avg_monthly_txn_amount=2000.0)
    )
    assert ctx.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert ctx.recommended_action in (Action.ESCALATE, Action.BLOCK)
    print("PASS test_pep_customer")


def test_false_positive_reduction():
    ctx = orchestrator.investigate(
        make_txn(amount=150.0, country="CA"),
        make_customer(account_age_days=900, kyc_status="verified")
    )
    assert ctx.recommended_action != Action.BLOCK
    print("PASS test_false_positive_reduction")


def test_report_structure():
    ctx = orchestrator.investigate(make_txn(amount=9800.0), make_customer())
    report = orchestrator.to_report(ctx)
    required_keys = {"case_id", "fraud_risk_score", "risk_level", "confidence",
                     "recommended_action", "explanation", "signals", "audit_trail"}
    assert required_keys.issubset(report.keys())
    print("PASS test_report_structure")


if __name__ == "__main__":
    test_clean_transaction()
    test_structuring_detection()
    test_high_risk_geo()
    test_pep_customer()
    test_false_positive_reduction()
    test_report_structure()
    print("\nAll tests passed!")
