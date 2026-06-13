"""Generate the membership contract PDF (design steps: individual 5, provider 3).

The contract fixes pricing at cogs + markup% and a fixed $20/mo payment. Pure
reportlab, returns PDF bytes — no temp files.
"""

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from backend import config


def build_contract(
    hospital_name: str,
    individual_name: str,
    btc_address: str | None = None,
    npub: str | None = None,
    monthly_usd: float | None = None,
    markup_pct: float | None = None,
    services: list[str] | None = None,
    signed_date: str | None = None,
) -> bytes:
    monthly_usd = config.PLAN_MONTHLY_USD if monthly_usd is None else monthly_usd
    markup_pct = config.PLAN_MARKUP_PCT if markup_pct is None else markup_pct
    signed_date = signed_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        leftMargin=1 * inch, rightMargin=1 * inch,
        title="Project Hidra Membership Contract",
    )
    styles = getSampleStyleSheet()
    h = ParagraphStyle("Hidra", parent=styles["Title"], fontSize=18, spaceAfter=6)
    body = styles["BodyText"]
    body.spaceAfter = 8

    story = [
        Paragraph("Project Hidra — Membership Agreement", h),
        Paragraph(f"Executed {signed_date} (UTC)", styles["Normal"]),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"This agreement is between <b>{individual_name or '—'}</b> (the "
            f"&ldquo;Member&rdquo;) and <b>{hospital_name or '—'}</b> (the "
            f"&ldquo;Provider&rdquo;).",
            body,
        ),
    ]

    terms = [
        ["Term", "Value"],
        ["Monthly payment", f"${monthly_usd:.2f} per month, paid in BTC"],
        ["Service pricing", f"Cost of goods/services (COGS) + {markup_pct:.0f}%"],
        ["Services covered", ", ".join(services) if services else "Per provider plan"],
        ["Provider BTC address", btc_address or "—"],
        ["Member ID (npub)", npub or "—"],
    ]
    table = Table(terms, colWidths=[2.1 * inch, 3.9 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f62fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 0.15 * inch), table, Spacer(1, 0.25 * inch)]

    clauses = [
        f"1. The Member agrees to pay ${monthly_usd:.2f} per month in Bitcoin to the "
        "Provider's address above. Payment is tracked on the public blockchain ledger.",
        f"2. In consideration, the Provider agrees to offer covered services to the "
        f"Member at a price of COGS + {markup_pct:.0f}% for the duration of membership.",
        "3. The Member's identity is represented by an encrypted Nostr key (npub). All "
        "communication occurs over encrypted direct messages.",
        "4. Either party may terminate by ceasing payment / service. No personal health "
        "information is disclosed in any resulting publication.",
    ]
    for c in clauses:
        story.append(Paragraph(c, body))

    story += [
        Spacer(1, 0.5 * inch),
        Table(
            [["_______________________", "_______________________"],
             [f"Member: {individual_name or ''}", f"Provider: {hospital_name or ''}"]],
            colWidths=[3 * inch, 3 * inch],
            style=TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9),
                              ("TOPPADDING", (0, 0), (-1, -1), 2)]),
        ),
    ]

    doc.build(story)
    return buf.getvalue()
