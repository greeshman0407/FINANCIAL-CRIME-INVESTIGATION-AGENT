"""
Demo: Full example input → output investigation case.
Run: python demo.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from core.models import Transaction, CustomerProfile
from core.orchestrator import InvestigationOrchestrator

orchestrator = InvestigationOrchestrator()

# ── Example 1: Structuring + PEP ─────────────────────────────────────────────
print("=" * 65)
print("CASE 1: Suspected Structuring by PEP Customer")
print("=" * 65)

txn = Transaction(
    transaction_id="TXN_20240115_001",
    account_id="ACC_SUSPECT_007",
    amount=9750.00,
    currency="USD",
    country="AE",                    # UAE — different from residence
    merchant_category="wire_transfer",
    timestamp=datetime(2024, 1, 15, 14, 32, 0),
    counterparty_id="ACC_SHELL_001",
    channel="online",
)

customer = CustomerProfile(
    account_id="ACC_SUSPECT_007",
    name="<redacted_name>",
    country_of_residence="US",
    kyc_status="verified",
    account_age_days=180,
    avg_monthly_txn_amount=4000.0,
    occupation="government_official",
    pep_flag=True,
)

ctx = orchestrator.investigate(txn, customer)
report = orchestrator.to_report(ctx)

print(f"\n[SCORE]  FRAUD RISK SCORE : {report['fraud_risk_score']:.3f}")
print(f"[LEVEL]  RISK LEVEL       : {report['risk_level']}")
print(f"[CONF]   CONFIDENCE       : {report['confidence']:.0%}")
print(f"[ACTION] ACTION           : {report['recommended_action']}")
print(f"\n[EXPLANATION]:\n{report['explanation']}")
print(f"\n[SIGNALS DETECTED ({len(report['signals'])})]:")
for s in report["signals"]:
    print(f"   [{s['severity']:.2f}] {s['type']}: {s['description']}")
print(f"\n[AUDIT TRAIL ({len(report['audit_trail'])} entries)]:")
for entry in report["audit_trail"]:
    print(f"   {entry['timestamp']} | {entry['agent']}: {entry['message']}")


# ── Example 2: Clean transaction ─────────────────────────────────────────────
print("\n" + "=" * 65)
print("CASE 2: Normal Transaction (should PASS)")
print("=" * 65)

txn2 = Transaction(
    transaction_id="TXN_20240115_002",
    account_id="ACC_NORMAL_001",
    amount=85.00,
    currency="USD",
    country="US",
    merchant_category="grocery",
    timestamp=datetime(2024, 1, 15, 10, 0, 0),
)

customer2 = CustomerProfile(
    account_id="ACC_NORMAL_001",
    name="<redacted_name>",
    country_of_residence="US",
    kyc_status="verified",
    account_age_days=1200,
    avg_monthly_txn_amount=2500.0,
    occupation="teacher",
)

ctx2 = orchestrator.investigate(txn2, customer2)
report2 = orchestrator.to_report(ctx2)
print(f"\n[SCORE] RISK SCORE: {report2['fraud_risk_score']:.3f} | ACTION: {report2['recommended_action']}")
print(f"   Signals: {len(report2['signals'])} | Audit entries: {len(report2['audit_trail'])}")
