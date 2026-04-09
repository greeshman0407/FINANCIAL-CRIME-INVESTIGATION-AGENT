"""Flask web server — serves dashboard UI and investigation API."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response
from functools import wraps
from datetime import datetime, timezone
from core.models import Transaction, CustomerProfile
from core.orchestrator import InvestigationOrchestrator
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False

app = Flask(__name__, template_folder="web")
app.secret_key = "finguard-secret-2024"
orchestrator = InvestigationOrchestrator()

# ── Allowed users (username → password) ──────────────────────────────────────
ALLOWED_USERS = {
    "cyberpunk": "cyber",
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if ALLOWED_USERS.get(username) == password:
            session["user"] = username
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session["user"])


@app.route("/api/investigate", methods=["POST"])
@login_required
def investigate():
    data = request.json

    txn = Transaction(
        transaction_id=data.get("transaction_id", "TXN_" + datetime.now().strftime("%Y%m%d%H%M%S")),
        account_id=data["account_id"],
        amount=float(data["amount"]),
        currency=data.get("currency", "INR"),
        country=data["country"],
        merchant_category=data["merchant_category"],
        timestamp=datetime.now(timezone.utc),
        counterparty_id=data.get("counterparty_id") or None,
        channel=data.get("channel", "online"),
    )

    customer = CustomerProfile(
        account_id=data["account_id"],
        name=data.get("name", "Unknown"),
        country_of_residence=data["residence_country"],
        kyc_status=data.get("kyc_status", "verified"),
        account_age_days=int(data.get("account_age_days", 365)),
        avg_monthly_txn_amount=float(data.get("avg_monthly_txn_amount", 3000)),
        occupation=data.get("occupation", "unknown"),
        pep_flag=data.get("pep_flag", False),
    )

    ctx = orchestrator.investigate(txn, customer)
    report = orchestrator.to_report(ctx)

    # Serialize enums to strings
    report["risk_level"] = ctx.risk_level.value
    report["recommended_action"] = ctx.recommended_action.value
    return jsonify(report)


@app.route("/api/report/pdf", methods=["POST"])
@login_required
def export_pdf():
    if not PDF_ENABLED:
        return jsonify({"error": "reportlab not installed. Run: pip install reportlab"}), 500

    data = request.json
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    DARK  = colors.HexColor("#0c1829")
    BLUE  = colors.HexColor("#3b82f6")
    WHITE = colors.white
    RISK_COLORS = {"LOW": colors.HexColor("#22c55e"), "MEDIUM": colors.HexColor("#f59e0b"),
                   "HIGH": colors.HexColor("#ef4444"), "CRITICAL": colors.HexColor("#a855f7")}

    title_style  = ParagraphStyle("title",  fontSize=18, textColor=BLUE,  fontName="Helvetica-Bold", spaceAfter=4, alignment=TA_CENTER)
    sub_style    = ParagraphStyle("sub",    fontSize=9,  textColor=colors.HexColor("#6b8aaa"), alignment=TA_CENTER, spaceAfter=16)
    h2_style     = ParagraphStyle("h2",     fontSize=11, textColor=BLUE,  fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)
    body_style   = ParagraphStyle("body",   fontSize=9,  textColor=colors.HexColor("#334155"), leading=14)
    mono_style   = ParagraphStyle("mono",   fontSize=8,  textColor=colors.HexColor("#475569"), fontName="Courier", leading=13)

    level  = data.get("risk_level", "LOW")
    action = data.get("recommended_action", "PASS")
    score  = data.get("fraud_risk_score", 0)
    conf   = data.get("confidence", 0)

    story = []
    story.append(Paragraph("FinGuard", title_style))
    story.append(Paragraph("Financial Crime Investigation Report", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE))
    story.append(Spacer(1, 10))

    # Summary table
    rc = RISK_COLORS.get(level, BLUE)
    summary_data = [
        ["Case ID", data.get("case_id", ""), "Risk Level", level],
        ["Transaction ID", data.get("transaction_id", ""), "Risk Score", f"{score:.3f}"],
        ["Account ID", data.get("account_id", ""), "Confidence", f"{int(conf*100)}%"],
        ["Action", action, "Signals", str(len(data.get("signals", [])))],
    ]
    t = Table(summary_data, colWidths=[3.5*cm, 6*cm, 3.5*cm, 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ("BACKGROUND",  (0,0), (0,-1), colors.HexColor("#e2e8f0")),
        ("BACKGROUND",  (2,0), (2,-1), colors.HexColor("#e2e8f0")),
        ("TEXTCOLOR",   (0,0), (-1,-1), colors.HexColor("#1e293b")),
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 8),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.HexColor("#f1f5f9")]),
        ("PADDING",     (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Signals
    story.append(Paragraph("Detected Signals", h2_style))
    signals = data.get("signals", [])
    if signals:
        sig_data = [["#", "Signal Type", "Severity", "Description"]]
        for i, s in enumerate(signals, 1):
            sig_data.append([str(i), s["type"].replace("_"," ").upper(), f"{int(s['severity']*100)}%", s["description"]])
        st = Table(sig_data, colWidths=[0.8*cm, 4*cm, 2*cm, 10.2*cm])
        st.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), BLUE),
            ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 8),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.HexColor("#f1f5f9")]),
            ("PADDING",     (0,0), (-1,-1), 5),
        ]))
        story.append(st)
    else:
        story.append(Paragraph("No signals detected.", body_style))

    # Explanation
    story.append(Paragraph("AI Investigation Narrative", h2_style))
    for line in data.get("explanation", "").split("\n"):
        story.append(Paragraph(line or " ", mono_style))

    # Audit trail
    story.append(Paragraph("Audit Trail", h2_style))
    audit = data.get("audit_trail", [])
    if audit:
        aud_data = [["Timestamp", "Agent", "Message"]]
        for e in audit:
            aud_data.append([e["timestamp"][:19], e["agent"], e["message"]])
        at = Table(aud_data, colWidths=[4.5*cm, 4*cm, 8.5*cm])
        at.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#334155")),
            ("TEXTCOLOR",   (0,0), (-1,0), WHITE),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 7),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING",     (0,0), (-1,-1), 4),
        ]))
        story.append(at)

    doc.build(story)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="finguard_{data.get("case_id","report")}.pdf"'
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5000)
