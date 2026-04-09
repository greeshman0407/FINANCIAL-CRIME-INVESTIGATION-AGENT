"""Anomaly Detection Agent — ML + rule-based hybrid."""
from core.models import AnomalySignal, InvestigationContext, Transaction, CustomerProfile
import math


# ── Rule-based checks ────────────────────────────────────────────────────────

def _check_amount_spike(txn: Transaction, profile: CustomerProfile) -> AnomalySignal | None:
    if profile.avg_monthly_txn_amount == 0:
        return None
    daily_avg = profile.avg_monthly_txn_amount / 30
    ratio = txn.amount / max(1, daily_avg)
    if ratio > 5:  # lowered threshold for earlier detection
        return AnomalySignal(
            signal_type="amount_spike",
            severity=min(1.0, ratio / 30),
            description=f"Transaction {ratio:.1f}x above daily average (₹{daily_avg:.0f})",
            evidence={"ratio": ratio, "txn_amount": txn.amount, "daily_avg": daily_avg}
        )
    return None


def _check_geo_anomaly(txn: Transaction, profile: CustomerProfile) -> AnomalySignal | None:
    HIGH_RISK_COUNTRIES = {"PK", "AF", "IR", "KP", "SY", "MM", "BD", "NP"}
    if txn.country != profile.country_of_residence:
        severity = 0.8 if txn.country in HIGH_RISK_COUNTRIES else 0.4
        return AnomalySignal(
            signal_type="geo_anomaly",
            severity=severity,
            description=f"Transaction in {txn.country}, customer resides in {profile.country_of_residence}",
            evidence={"txn_country": txn.country, "residence": profile.country_of_residence,
                      "high_risk": txn.country in HIGH_RISK_COUNTRIES}
        )
    return None


def _check_structuring(txn: Transaction) -> AnomalySignal | None:
    """Detect amounts just below RBI/FIU-IND reporting thresholds (structuring)."""
    THRESHOLDS = [1000000, 500000, 200000, 50000]  # INR thresholds
    for threshold in THRESHOLDS:
        if threshold * 0.80 <= txn.amount < threshold:
            severity = 0.85 if threshold >= 500000 else 0.65
            return AnomalySignal(
                signal_type="structuring",
                severity=severity,
                description=f"Amount ₹{txn.amount:.0f} is just below ₹{threshold} RBI reporting threshold",
                evidence={"amount": txn.amount, "threshold": threshold}
            )
    return None


def _check_kyc_risk(profile: CustomerProfile) -> AnomalySignal | None:
    if profile.kyc_status == "failed":
        return AnomalySignal(
            signal_type="kyc_incomplete",
            severity=0.85,
            description="Customer KYC has FAILED — high identity risk",
            evidence={"kyc_status": profile.kyc_status}
        )
    if profile.kyc_status == "pending":
        return AnomalySignal(
            signal_type="kyc_incomplete",
            severity=0.55,
            description="Customer KYC is pending verification",
            evidence={"kyc_status": profile.kyc_status}
        )
    if profile.pep_flag:
        return AnomalySignal(
            signal_type="pep_flag",
            severity=0.75,
            description="Customer is a Politically Exposed Person (PEP)",
            evidence={"pep": True}
        )
    return None


def _check_new_account(txn: Transaction, profile: CustomerProfile) -> AnomalySignal | None:
    if profile.account_age_days < 90 and txn.amount > 500:  # extended window
        severity = 0.80 if profile.account_age_days < 30 else 0.55
        return AnomalySignal(
            signal_type="new_account_large_txn",
            severity=severity,
            description=f"Account only {profile.account_age_days} days old with ₹{txn.amount:.0f} transaction",
            evidence={"account_age_days": profile.account_age_days, "amount": txn.amount}
        )
    return None


def _check_high_risk_occupation(profile: CustomerProfile, txn: Transaction) -> AnomalySignal | None:
    HIGH_RISK_OCC = {"government_official", "politician", "military", "unknown", "cash_business"}
    if profile.occupation.lower() in HIGH_RISK_OCC and txn.amount > 2000:
        return AnomalySignal(
            signal_type="high_risk_occupation",
            severity=0.60,
            description=f"High-risk occupation '{profile.occupation}' with large transaction",
            evidence={"occupation": profile.occupation, "amount": txn.amount}
        )
    return None


def _check_high_risk_merchant(txn: Transaction) -> AnomalySignal | None:
    HIGH_RISK = {"crypto": 0.65, "gambling": 0.70, "upi_transfer": 0.50, "neft_rtgs": 0.50, "gold_jewellery": 0.60}
    if txn.merchant_category in HIGH_RISK:
        return AnomalySignal(
            signal_type="high_risk_merchant",
            severity=HIGH_RISK[txn.merchant_category],
            description=f"Transaction via high-risk merchant category: {txn.merchant_category}",
            evidence={"merchant_category": txn.merchant_category}
        )
    return None


# ── ML-based score (lightweight isolation-forest-style heuristic) ─────────────

def _ml_anomaly_score(txn: Transaction, profile: CustomerProfile) -> float:
    """
    Improved anomaly score with more features and better normalization.
    In production: load a trained sklearn IsolationForest / AutoEncoder.
    Returns 0.0 (normal) to 1.0 (highly anomalous).
    """
    daily_avg = max(1, profile.avg_monthly_txn_amount / 30)
    HIGH_RISK_COUNTRIES = {"PK", "AF", "IR", "KP", "SY", "MM", "BD", "NP"}
    features = {
        "amount_zscore":      min(1.0, abs(txn.amount - daily_avg) / max(1, daily_avg)),
        "is_foreign":         float(txn.country != profile.country_of_residence),
        "high_risk_country":  float(txn.country in HIGH_RISK_COUNTRIES),
        "account_age_factor": max(0, 1 - profile.account_age_days / 730),
        "high_risk_merchant": float(txn.merchant_category in {"gambling", "crypto", "upi_transfer", "neft_rtgs", "gold_jewellery"}),
        "pep_factor":         float(profile.pep_flag),
        "kyc_factor":         0.8 if profile.kyc_status == "failed" else (0.4 if profile.kyc_status == "pending" else 0.0),
    }
    weights = {
        "amount_zscore": 0.25, "is_foreign": 0.15, "high_risk_country": 0.20,
        "account_age_factor": 0.10, "high_risk_merchant": 0.10,
        "pep_factor": 0.10, "kyc_factor": 0.10,
    }
    raw = sum(features[k] * weights[k] for k in features)
    return round(min(1.0, raw * 1.8), 3)  # scale up for better sensitivity


# ── Agent entry point ─────────────────────────────────────────────────────────

class AnomalyDetectionAgent:
    NAME = "AnomalyDetectionAgent"

    def run(self, ctx: InvestigationContext) -> InvestigationContext:
        txn, profile = ctx.transaction, ctx.customer
        ctx.log(self.NAME, "Starting anomaly detection")

        rule_checks = [
            _check_amount_spike(txn, profile),
            _check_geo_anomaly(txn, profile),
            _check_structuring(txn),
            _check_kyc_risk(profile),
            _check_new_account(txn, profile),
            _check_high_risk_occupation(profile, txn),
            _check_high_risk_merchant(txn),
        ]
        ctx.signals = [s for s in rule_checks if s is not None]

        ml_score = _ml_anomaly_score(txn, profile)
        if ml_score > 0.3:  # lower threshold for better recall
            ctx.signals.append(AnomalySignal(
                signal_type="ml_anomaly",
                severity=ml_score,
                description=f"ML model flagged transaction with anomaly score {ml_score:.2f}",
                evidence={"ml_score": ml_score}
            ))

        ctx.log(self.NAME, f"Detected {len(ctx.signals)} signals", {"signals": [s.signal_type for s in ctx.signals]})
        return ctx
