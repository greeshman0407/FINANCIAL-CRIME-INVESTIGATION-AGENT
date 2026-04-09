"""FastAPI service — exposes the investigation pipeline as a REST API."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from core.models import Transaction, CustomerProfile
from core.orchestrator import InvestigationOrchestrator

app = FastAPI(title="Financial Crime Investigation API", version="1.0")
orchestrator = InvestigationOrchestrator()


# ── Request / Response schemas ────────────────────────────────────────────────

class TransactionRequest(BaseModel):
    transaction_id: str
    account_id: str
    amount: float
    currency: str = "USD"
    country: str
    merchant_category: str
    timestamp: datetime
    counterparty_id: str | None = None
    channel: str = "online"


class CustomerRequest(BaseModel):
    account_id: str
    name: str
    country_of_residence: str
    kyc_status: str
    account_age_days: int
    avg_monthly_txn_amount: float
    occupation: str
    pep_flag: bool = False


class InvestigationRequest(BaseModel):
    transaction: TransactionRequest
    customer: CustomerRequest


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/investigate")
def investigate(request: InvestigationRequest):
    txn = Transaction(**request.transaction.model_dump())
    customer = CustomerProfile(**request.customer.model_dump())

    if txn.account_id != customer.account_id:
        raise HTTPException(status_code=400, detail="Transaction and customer account_id mismatch")

    ctx = orchestrator.investigate(txn, customer)
    return orchestrator.to_report(ctx)


@app.get("/health")
def health():
    return {"status": "ok"}
