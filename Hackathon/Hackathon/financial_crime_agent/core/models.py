"""Core data models for the investigation system."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Action(str, Enum):
    PASS = "PASS"
    MONITOR = "MONITOR"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


@dataclass
class Transaction:
    transaction_id: str
    account_id: str
    amount: float
    currency: str
    country: str
    merchant_category: str
    timestamp: datetime
    counterparty_id: str | None = None
    channel: str = "online"  # online, atm, branch


@dataclass
class CustomerProfile:
    account_id: str
    name: str
    country_of_residence: str
    kyc_status: str          # verified, pending, failed
    account_age_days: int
    avg_monthly_txn_amount: float
    occupation: str
    pep_flag: bool = False   # Politically Exposed Person
    sanctions_hit: bool = False


@dataclass
class AnomalySignal:
    signal_type: str         # amount_spike, velocity, geo_anomaly, etc.
    severity: float          # 0.0 - 1.0
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvestigationContext:
    """Shared state passed between all agents."""
    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction: Transaction | None = None
    customer: CustomerProfile | None = None
    signals: list[AnomalySignal] = field(default_factory=list)
    enrichment_data: dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    explanation: str = ""
    recommended_action: Action = Action.PASS
    confidence: float = 0.0
    audit_trail: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def log(self, agent: str, message: str, data: dict | None = None):
        self.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "message": message,
            "data": data or {}
        })
