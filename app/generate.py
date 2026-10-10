"""Generates a labelled test set of synthetic invoices (PDFs and 'scanned' images) with ground truth.

Variety on purpose: 3 layouts, US/Indian/European vendors, different date formats, Indian digit grouping
(1,23,456.00), European decimals (1.234,50), optional discounts and due dates, different labels for the same
field, and two 'trap' invoices whose printed total does not add up (a real vendor mistake the system must flag).

Usage:  python -m app.generate            (writes data/samples/ + ground_truth.json)
"""
from __future__ import annotations

import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

from app.config import get_settings

VENDORS = [
    # name, address lines, country, currency, tax label, rate, date style, number style
    ("Northwind Office Supply", ["1840 Market St, Suite 300", "San Francisco, CA 94103, USA"], "US", "USD", "Sales Tax 8.5%", 0.085, "us", "us"),
    ("Cobalt Cloud Services LLC", ["77 Water Street", "New York, NY 10005, USA"], "US", "USD", "Sales Tax 8.875%", 0.08875, "us", "us"),
    ("Pinecrest Print & Signs", ["410 Oak Ave", "Austin, TX 78701, USA"], "US", "USD", "Sales Tax 8.25%", 0.0825, "long", "us"),
    ("Sharma Packaging Pvt. Ltd.", ["Plot 12, MIDC Industrial Area", "Pune, Maharashtra 411019, India"], "IN", "INR", "GST 18%", 0.18, "in", "in"),
    ("Kaveri Logistics LLP", ["3rd Floor, Brigade Towers", "Bengaluru, Karnataka 560001, India"], "IN", "INR", "IGST 18%", 0.18, "short", "in"),
    ("Ganga Textiles", ["Sector 5, Salt Lake", "Kolkata, West Bengal 700091, India"], "IN", "INR", "GST 12%", 0.12, "in", "in"),
    ("Brandt Maschinenbau GmbH", ["Industriestrasse 14", "70565 Stuttgart, Germany"], "DE", "EUR", "MwSt. 19%", 0.19, "eu", "eu"),
    ("Atelier Lumiere SARL", ["22 Rue de la Paix", "75002 Paris, France"], "FR", "EUR", "TVA 20%", 0.20, "eu", "eu"),
    ("Harbourside Digital Ltd", ["5 Canal Wharf", "Leeds LS11 5PZ, United Kingdom"], "GB", "GBP", "VAT 20%", 0.20, "long", "us"),
]

ITEMS = {
    "USD": [("Printer paper, A4 (box of 10 reams)", 42.5), ("Toner cartridge, black", 89.99), ("Cloud hosting, monthly plan", 249.0),
            ("Managed backup, 1 TB", 59.0), ("Vinyl banner, 3 x 6 ft", 118.0), ("Business cards (500)", 36.75),
            ("Ergonomic office chair", 329.0), ("Standing desk frame", 412.0), ("Support hours", 95.0)],
    "INR": [("Corrugated boxes, 5-ply", 38.0), ("Bubble wrap roll, 50 m", 650.0), ("Freight: Pune to Mumbai", 7800.0),
            ("Warehouse handling charges", 2400.0), ("Cotton fabric, per metre", 185.0), ("Packing tape (pack of 12)", 540.0),
            ("Courier charges, express", 1250.0), ("Pallet rental, per day", 320.0)],
    "EUR": [("Bearing assembly, type B-40", 214.0), ("Hydraulic seal kit", 86.4), ("Maintenance visit", 640.0),
            ("Design consultation, per hour", 120.0), ("Linen drapery, per metre", 48.5), ("Brass fittings set", 72.0)],
    "GBP": [("Website maintenance, monthly", 450.0), ("SEO audit", 1200.0), ("Content writing, per article", 180.0),
            ("Hosting, annual", 360.0), ("Design hours", 85.0)],
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
LABELS = {
    "number": ["Invoice No.", "Invoice #", "Bill No.", "Invoice Number"],
    "date": ["Invoice Date", "Date", "Date of Issue", "Bill Date"],
    "due": ["Due Date", "Payment Due", "Pay By"],
    "total": ["Total", "Amount Due", "Grand Total", "Total Payable"],
}


def fmt_date(d: date, style: str) -> str:
    return {"us": d.strftime("%m/%d/%Y"), "in": d.strftime("%d-%m-%Y"), "eu": d.strftime("%d.%m.%Y"),
            "long": f"{MONTHS[d.month - 1]} {d.day}, {d.year}", "short": d.strftime("%d %b %Y")}[style]


def fmt_num(v: float, style: str) -> str:
    if style == "eu":
        s = f"{v:,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    if style == "in":
        whole, frac = f"{v:.2f}".split(".")
        neg = whole.startswith("-")
        whole = whole.lstrip("-")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            whole = ",".join(groups) + "," + tail
        return ("-" if neg else "") + whole + "." + frac
    return f"{v:,.2f}"


def money(v: float, cur: str, style: str) -> str:
    sym = {"USD": "$", "EUR": "EUR ", "GBP": "GBP ", "INR": "Rs. "}[cur]
    return f"{sym}{fmt_num(v, style)}" if cur != "EUR" else f"{fmt_num(v, style)} EUR"


def make_invoice(rng: random.Random, n: int, trap: bool = False) -> dict:
    v = rng.choice(VENDORS)
    name, addr, country, cur, tax_label, rate, dstyle, nstyle = v
    day = date(2026, rng.randint(1, 9), rng.randint(13, 28))          # day > 12: numeric dates are unambiguous
    due = day + timedelta(days=rng.choice([15, 30, 45])) if rng.random() < 0.75 else None
    items = []
    for desc, price in rng.sample(ITEMS[cur], rng.randint(2, 5)):
        qty = rng.choice([1, 1, 2, 3, 4, 5, 10, 12, 25]) if price < 500 else rng.choice([1, 1, 2])
        unit = round(price * rng.uniform(0.9, 1.1), 2)
        items.append({"description": desc, "quantity": qty, "unit_price": unit, "amount": round(qty * unit, 2)})
    subtotal = round(sum(i["amount"] for i in items), 2)
    discount = round(subtotal * rng.choice([0.05, 0.1]), 2) if rng.random() < 0.3 else 0.0
    tax = round((subtotal - discount) * rate, 2)
    total = round(subtotal - discount + tax, 2)
    if trap:
        total = round(total + rng.choice([10.0, 100.0, 25.5]), 2)      # vendor arithmetic mistake, printed as-is
    prefix = {"US": "INV", "IN": "SPL/26-27/", "DE": "RE-", "FR": "FA", "GB": "HD-"}[country]
    number = f"{prefix}{rng.randint(1000, 9999)}" if country != "IN" else f"{prefix}{rng.randint(100, 999)}"
    return {
        "doc_id": f"INV{n:03d}", "layout": rng.choice(["classic", "band", "compact"]), "trap": trap,
        "vendor": name, "vendor_address": addr, "country": country, "invoice_number": number,
        "invoice_date": day.isoformat(), "due_date": due.isoformat() if due else None, "currency": cur,
        "subtotal": subtotal, "discount": discount, "tax": tax, "tax_label": tax_label, "total": total,
        "line_items": items, "date_style": dstyle, "num_style": nstyle,
        "labels": {k: rng.choice(opts) for k, opts in LABELS.items()},
        "bill_to": rng.choice(["Vedang Analytics, Kolkata, India", "Loom & Ladle Inc., Reno, NV, USA",
                               "Acme Retail Ltd., London, UK", "Bluebird Studios, Lisbon, Portugal"]),
    }


def render_pdf(inv: dict) -> bytes:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    ds, ns, cur, lab = inv["date_style"], inv["num_style"], inv["currency"], inv["labels"]
    m = lambda v: money(v, cur, ns)
    accent = HexColor(random.Random(inv["doc_id"]).choice(["#1F3A5F", "#7A2E2E", "#2F5D50", "#4B3B6B"]))
    L, R = 50, W - 50

    if inv["layout"] == "band":
        c.setFillColor(accent); c.rect(0, H - 110, W, 110, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 20); c.drawString(L, H - 55, inv["vendor"])
        c.setFont("Helvetica", 9)
        for i, line in enumerate(inv["vendor_address"]):
            c.drawString(L, H - 72 - i * 12, line)
        c.setFont("Helvetica-Bold", 26); c.drawRightString(R, H - 60, "INVOICE")
        c.setFillColor(HexColor("#111111")); y = H - 150
    else:
        c.setFillColor(accent); c.setFont("Helvetica-Bold", 18 if inv["layout"] == "classic" else 15)
        c.drawString(L, H - 60, inv["vendor"])
        c.setFillColor(HexColor("#333333")); c.setFont("Helvetica", 9)
        for i, line in enumerate(inv["vendor_address"]):
            c.drawString(L, H - 76 - i * 12, line)
        c.setFont("Helvetica-Bold", 22 if inv["layout"] == "classic" else 16)
        c.drawRightString(R, H - 60, "TAX INVOICE" if inv["country"] == "IN" else "INVOICE")
        c.setFillColor(HexColor("#111111")); y = H - 140

    meta = [(lab["number"], inv["invoice_number"]), (lab["date"], fmt_date(date.fromisoformat(inv["invoice_date"]), ds))]
    if inv["due_date"]:
        meta.append((lab["due"], fmt_date(date.fromisoformat(inv["due_date"]), ds)))
    c.setFont("Helvetica-Bold", 9); c.drawString(L, y, "Bill to"); c.setFont("Helvetica", 10); c.drawString(L, y - 14, inv["bill_to"])
    for i, (k, v) in enumerate(meta):
        c.setFont("Helvetica-Bold", 9); c.drawRightString(R - 120, y - i * 15, k + ":")
        c.setFont("Helvetica", 10); c.drawRightString(R, y - i * 15, v)

    y -= 70
    cols = [L, L + 280, L + 340, R] if inv["layout"] != "compact" else [L, L + 300, L + 350, R]
    c.setFillColor(accent if inv["layout"] != "compact" else HexColor("#DDDDDD"))
    c.rect(L - 4, y - 5, R - L + 8, 18, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF") if inv["layout"] != "compact" else HexColor("#111111")); c.setFont("Helvetica-Bold", 9)
    c.drawString(cols[0], y, "Description"); c.drawRightString(cols[1], y, "Qty")
    c.drawRightString(cols[2] + 70, y, "Unit price"); c.drawRightString(cols[3], y, "Amount")
    c.setFillColor(HexColor("#111111")); c.setFont("Helvetica", 10)
    for it in inv["line_items"]:
        y -= 20
        c.drawString(cols[0], y, it["description"]); c.drawRightString(cols[1], y, str(it["quantity"]))
        c.drawRightString(cols[2] + 70, y, fmt_num(it["unit_price"], ns)); c.drawRightString(cols[3], y, fmt_num(it["amount"], ns))
        c.setStrokeColor(HexColor("#E2E2E2")); c.line(L, y - 6, R, y - 6)

    y -= 34
    rows = [("Subtotal", inv["subtotal"])]
    if inv["discount"]:
        rows.append(("Discount", -inv["discount"]))
    rows.append((inv["tax_label"], inv["tax"]))
    for k, v in rows:
        c.setFont("Helvetica", 10); c.drawRightString(R - 130, y, k); c.drawRightString(R, y, m(v)); y -= 16
    c.setFont("Helvetica-Bold", 12); c.drawRightString(R - 130, y - 4, lab["total"]); c.drawRightString(R, y - 4, m(inv["total"]))

    c.setFont("Helvetica", 8); c.setFillColor(HexColor("#666666"))
    note = {"IN": "Subject to Pune jurisdiction. E. & O.E.", "DE": "Zahlbar ohne Abzug.", "FR": "Paiement a reception."}
    c.drawString(L, 60, note.get(inv["country"], "Thank you for your business."))
    c.showPage(); c.save()
    return buf.getvalue()


def to_scan(pdf: bytes, seed: str, hard: bool = False) -> bytes:
    """Rasterises a PDF page and degrades it like a scan. hard=True mimics a poor phone photo of a fax:
    lower resolution, stronger tilt, blur, noise and heavy JPEG compression."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter
    rng = random.Random(seed)
    page = pdfium.PdfDocument(pdf)[0]
    img = page.render(scale=0.95 if hard else 1.25).to_pil().convert("L")
    tilt = rng.uniform(2.2, 3.5) * rng.choice([-1, 1]) if hard else rng.uniform(-1.8, 1.8)
    img = img.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=235 if hard else 245)
    noise = Image.effect_noise(img.size, 30 if hard else 18).convert("L")
    img = Image.blend(img, noise, 0.14 if hard else 0.08).filter(ImageFilter.GaussianBlur(1.0 if hard else 0.6))
    img = img.point(lambda p: min(255, int(p * (0.85 if hard else 0.92) + (30 if hard else 18))))
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=38 if hard else 70)
    return out.getvalue()


NUMBER_PATTERNS = {"US": r"INV\d{4}", "IN": r"SPL/26-27/\d{3}", "DE": r"RE-\d{4}", "FR": r"FA\d{4}", "GB": r"HD-\d{4}"}


def vendor_master() -> list[dict]:
    """The supplier list an accounts-payable team keeps: known names, invoice-number formats and currencies."""
    return [{"name": v[0], "aliases": [], "invoice_number_pattern": NUMBER_PATTERNS[v[2]], "currency": v[3]} for v in VENDORS]


def printed_extraction(t: dict) -> dict:
    """What an ideal model returns for a ground-truth record: values plus the text exactly as printed."""
    v = next(x for x in VENDORS if x[0] == t["vendor"])
    ds, ns, cur = v[6], v[7], t["currency"]
    m = lambda x: money(x, cur, ns)
    d = lambda x: fmt_date(date.fromisoformat(x), ds) if x else None
    return {
        "vendor": {"value": t["vendor"], "evidence": t["vendor"]},
        "invoice_number": {"value": t["invoice_number"], "evidence": t["invoice_number"]},
        "invoice_date": {"value": t["invoice_date"], "evidence": d(t["invoice_date"])},
        "due_date": {"value": t["due_date"], "evidence": d(t["due_date"])},
        "currency": {"value": cur, "evidence": m(1).split()[0] if cur != "EUR" else "EUR"},
        "subtotal": {"value": t["subtotal"], "evidence": m(t["subtotal"])},
        "discount": {"value": t["discount"] or None, "evidence": m(t["discount"]) if t["discount"] else None},
        "tax": {"value": t["tax"], "evidence": m(t["tax"])},
        "total": {"value": t["total"], "evidence": m(t["total"])},
        "line_items": [dict(i) for i in t["line_items"]],
        "uncertain_fields": [],
    }


TRUTH_FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "discount", "tax",
                "total", "line_items"]


def generate(out_dir: Path, n: int = 30, n_hard: int = 10, seed: int = 7) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("INV*.*"):
        old.unlink()
    rng = random.Random(seed)
    traps = {8, 23}
    truth = []
    for k in range(1, n + n_hard + 1):
        inv = make_invoice(rng, k, trap=k in traps)
        pdf = render_pdf(inv)
        hard = k > n                            # the last n_hard documents are poor-quality scans
        scanned = hard or k % 5 in (2, 4)       # plus 40% ordinary scans in the main set
        kind = "hard_scan" if hard else "scan" if scanned else "digital"
        fname = f"{inv['doc_id']}.{'jpg' if scanned else 'pdf'}"
        (out_dir / fname).write_bytes(to_scan(pdf, inv["doc_id"], hard) if scanned else pdf)
        truth.append({"file": fname, "kind": kind, "trap": inv["trap"],
                      "layout": inv["layout"], "country": inv["country"],
                      **{f: inv[f] for f in TRUTH_FIELDS}})
    path = out_dir / "ground_truth.json"
    path.write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    s = get_settings()
    print(f"Wrote {generate(s.samples_dir)}")
    s.vendors_path.parent.mkdir(parents=True, exist_ok=True)
    s.vendors_path.write_text(json.dumps(vendor_master(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {s.vendors_path}")
