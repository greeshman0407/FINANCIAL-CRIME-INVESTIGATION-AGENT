"""Data Enrichment Agent — real APIs: OpenSanctions, GDELT, IBAN + SQLite velocity."""
import sqlite3, os, requests
from datetime import datetime, timezone, timedelta
from core.models import InvestigationContext

# ── DB path ───────────────────────────────────────────────────────────────────
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "transactions.db")


# ── 1. SQLite velocity tracking ───────────────────────────────────────────────

def _init_db():
    con = sqlite3.connect(_DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            account_id TEXT,
            country    TEXT,
            ts         TEXT
        )
    """)
    con.commit()
    con.close()


def _record_transaction(account_id: str, country: str):
    _init_db()
    con = sqlite3.connect(_DB_PATH)
    con.execute("INSERT INTO transactions VALUES (?, ?, ?)",
                (account_id, country, datetime.now(timezone.utc).isoformat()))
    con.commit()
    con.close()


def _get_velocity(account_id: str) -> dict:
    _init_db()
    con = sqlite3.connect(_DB_PATH)
    now = datetime.now(timezone.utc)
    t24h = (now - timedelta(hours=24)).isoformat()
    t7d  = (now - timedelta(days=7)).isoformat()

    count_24h = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id=? AND ts>=?",
        (account_id, t24h)
    ).fetchone()[0]

    rows_7d = con.execute(
        "SELECT country FROM transactions WHERE account_id=? AND ts>=?",
        (account_id, t7d)
    ).fetchall()
    con.close()

    return {
        "txn_count_24h":      count_24h,
        "txn_count_7d":       len(rows_7d),
        "unique_countries_7d": len({r[0] for r in rows_7d}),
    }


# ── 2. OpenSanctions API ──────────────────────────────────────────────────────
# Docs: https://www.opensanctions.org/api/
_OPENSANCTIONS_URL = "https://api.opensanctions.org/match/default"
_OPENSANCTIONS_KEY = os.getenv("OPENSANCTIONS_API_KEY", "")  # free key at opensanctions.org


def _check_sanctions(name: str, counterparty_id: str | None) -> dict:
    hits = []
    for query_name in filter(None, [name, counterparty_id]):
        try:
            headers = {"Authorization": f"ApiKey {_OPENSANCTIONS_KEY}"} if _OPENSANCTIONS_KEY else {}
            resp = requests.post(
                _OPENSANCTIONS_URL,
                json={"queries": {"q": {"schema": "Person", "properties": {"name": [query_name]}}}},
                headers=headers,
                timeout=6,
            )
            if resp.status_code == 200:
                results = resp.json().get("responses", {}).get("q", {}).get("results", [])
                for r in results[:2]:
                    if r.get("score", 0) >= 0.7:
                        hits.append({
                            "name":    r.get("caption", query_name),
                            "score":   r.get("score"),
                            "datasets": r.get("datasets", []),
                            "list":    "OpenSanctions",
                        })
        except Exception:
            pass
    return {"sanctions_hits": hits, "is_sanctioned": len(hits) > 0}


# ── 3. GDELT adverse news ─────────────────────────────────────────────────────
# Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _get_adverse_news(name: str) -> list[str]:
    if not name or name.lower() in ("unknown", "jane doe", "john smith"):
        return []
    try:
        resp = requests.get(_GDELT_URL, params={
            "query":      f'"{name}" (fraud OR money laundering OR sanctions OR corruption)',
            "mode":       "ArtList",
            "maxrecords": 5,
            "format":     "json",
            "timespan":   "1y",
        }, timeout=6)
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            return [a["title"] for a in articles if a.get("title")]
    except Exception:
        pass
    return []


# ── 4. IBAN / BIC validation ──────────────────────────────────────────────────
# Uses ibanapi.com — free tier, no key needed for basic validation
_IBAN_URL = "https://api.ibanapi.com/v1/validate/"
_IBAN_KEY  = os.getenv("IBAN_API_KEY", "")  # free key at ibanapi.com


def _validate_iban(counterparty_id: str | None) -> dict:
    """Validate counterparty ID as IBAN if it looks like one (starts with 2 letters + digits)."""
    if not counterparty_id:
        return {"iban_valid": None, "bank_name": None, "bank_country": None}

    # Only attempt if it looks like an IBAN
    stripped = counterparty_id.replace(" ", "").upper()
    if not (len(stripped) >= 15 and stripped[:2].isalpha() and stripped[2:4].isdigit()):
        return {"iban_valid": None, "bank_name": None, "bank_country": None}

    try:
        url = f"{_IBAN_URL}{stripped}"
        params = {"api_key": _IBAN_KEY} if _IBAN_KEY else {}
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            bank = data.get("data", {}).get("bank_data", {})
            return {
                "iban_valid":   data.get("result") == 200,
                "bank_name":    bank.get("bank", "Unknown"),
                "bank_country": bank.get("country", "Unknown"),
            }
    except Exception:
        pass
    return {"iban_valid": None, "bank_name": None, "bank_country": None}


# ── 5. Network risk (kept from original) ─────────────────────────────────────
_HIGH_RISK_NETWORK = {"ACC_SHELL_001", "ACC_MULE_002"}


def _get_network_risk(counterparty_id: str | None) -> dict:
    if counterparty_id in _HIGH_RISK_NETWORK:
        return {"network_risk": True, "reason": "Counterparty linked to known money mule network"}
    return {"network_risk": False}


# ── Agent entry point ─────────────────────────────────────────────────────────

class DataEnrichmentAgent:
    NAME = "DataEnrichmentAgent"

    def run(self, ctx: InvestigationContext) -> InvestigationContext:
        ctx.log(self.NAME, "Starting data enrichment")

        txn        = ctx.transaction
        account_id = txn.account_id

        # Record this transaction for future velocity checks
        _record_transaction(account_id, txn.country)

        ctx.enrichment_data = {
            "sanctions":    _check_sanctions(ctx.customer.name, txn.counterparty_id),
            "velocity":     _get_velocity(account_id),
            "adverse_news": _get_adverse_news(ctx.customer.name),
            "iban":         _validate_iban(txn.counterparty_id),
            "network_risk": _get_network_risk(txn.counterparty_id),
        }

        if ctx.enrichment_data["sanctions"]["is_sanctioned"]:
            ctx.customer.sanctions_hit = True

        ctx.log(self.NAME, "Enrichment complete", {
            "sanctioned":         ctx.enrichment_data["sanctions"]["is_sanctioned"],
            "velocity_24h":       ctx.enrichment_data["velocity"]["txn_count_24h"],
            "adverse_news_count": len(ctx.enrichment_data["adverse_news"]),
            "iban_valid":         ctx.enrichment_data["iban"]["iban_valid"],
        })
        return ctx
