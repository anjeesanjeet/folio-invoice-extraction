"""Checks every extracted field in code. A field the checks can't confirm goes to a human; it is never trusted silently.

Checks
  required          vendor, number, date, currency and total must be present
  date_valid        dates parse, are plausible, and the due date is not before the invoice date
  evidence_match    the value is consistent with the text the model says it read (catches conversion slips)
  in_document       digital PDFs: the evidence actually appears in the PDF's text layer (catches invented values)
  line_math         quantity x unit price = amount, for every line
  items_sum         line amounts add up to the subtotal
  total_math        subtotal - discount + tax = total
  tax_rate          tax is a plausible share of the taxable amount
  currency          a known ISO currency code
  model_uncertain   the model itself flagged the field as hard to read
  vendor_known      the vendor matches the vendor master exactly (a near-miss means a misread or a new supplier)
  number_format     the invoice number fits that vendor's known format
  currency_match    the currency is the one that vendor bills in
(duplicate detection runs in the pipeline, because it needs the database)
"""
from __future__ import annotations

import re
from datetime import date, datetime

from app.extract import ALL_FIELDS

CURRENCIES = {"USD", "EUR", "GBP", "INR", "AUD", "CAD", "SGD", "AED", "JPY", "CHF", "CNY", "NZD", "ZAR", "SEK"}
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%B %d, %Y",
                "%b %d, %Y", "%d-%b-%Y", "%d %b, %Y"]


def parse_amount(text) -> float | None:
    """Parses 1,234.50 / 1.234,50 / 1,23,456.00 / Rs. 12,000 / $-12.5 into a float."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = str(text)
    m = re.search(r"\d[\d.,\s]*\d|\d", raw)          # the number itself, ignoring "Rs.", "$", "EUR"
    if not m:
        return None
    neg = "-" in raw[: m.start()] or raw.strip().startswith("(")
    s = re.sub(r"\s", "", m.group())
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{2}$", s) and s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(text) -> date | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", str(text).strip().rstrip("."))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def numbers_in(text: str) -> set[float]:
    return {round(v, 2) for tok in re.findall(r"\d[\d.,]*\d|\d", text or "") if (v := parse_amount(tok)) is not None}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= 0.011 + 0.00001 * abs(b)


def value_of(ext: dict, f: str):
    v = ext.get(f)
    return v.get("value") if isinstance(v, dict) else v


def match_vendor(name: str, vendors: list[dict]) -> tuple[dict | None, dict | None, float]:
    """Returns (exact match, closest entry, closest similarity)."""
    from difflib import SequenceMatcher
    n = _norm(name)
    best, best_r = None, 0.0
    for v in vendors:
        for cand in [v["name"], *v.get("aliases", [])]:
            if _norm(cand) == n:
                return v, v, 1.0
            r = SequenceMatcher(None, _norm(cand), n).ratio()
            if r > best_r:
                best, best_r = v, r
    return None, best, best_r


def validate(ext: dict, kind: str, text_layer: str = "", max_tax_rate: float = 0.30,
             vendors: list[dict] | None = None) -> dict:
    """Returns {"checks": [...], "fields": {field: {"status": ok|review, "reasons": [...]}}}."""
    reasons: dict[str, list[str]] = {f: [] for f in ALL_FIELDS}
    checks: list[dict] = []

    def check(name: str, passed: bool, fields: list[str], detail: str = ""):
        checks.append({"name": name, "passed": passed, "fields": fields, "detail": detail})
        if not passed:
            for f in fields:
                reasons[f].append(name + (f": {detail}" if detail else ""))

    num = lambda f: parse_amount(value_of(ext, f))
    sub, disc, tax, total = num("subtotal"), num("discount") or 0.0, num("tax"), num("total")
    items = ext.get("line_items") or []

    for f in ("vendor", "invoice_number", "invoice_date", "currency", "total"):
        v = value_of(ext, f)
        check("required", v not in (None, ""), [f], "missing" if v in (None, "") else "")

    inv_d, due_d = parse_date(value_of(ext, "invoice_date")), parse_date(value_of(ext, "due_date"))
    if value_of(ext, "invoice_date"):
        check("date_valid", bool(inv_d) and date(2000, 1, 1) <= inv_d <= date(2035, 12, 31), ["invoice_date"], "unparseable or implausible")
    if value_of(ext, "due_date"):
        ok = bool(due_d) and (inv_d is None or due_d >= inv_d)
        check("date_valid", ok, ["due_date"], "before invoice date" if due_d and inv_d and due_d < inv_d else "")

    numbers = numbers_in(text_layer) if kind == "digital" else set()
    for f in ALL_FIELDS[:-1]:
        fv = ext.get(f) if isinstance(ext.get(f), dict) else {}
        val, ev = fv.get("value"), fv.get("evidence")
        if val in (None, "") or not ev:
            continue
        if f in ("invoice_date", "due_date"):
            pe = parse_date(ev)
            if pe:
                check("evidence_match", pe == parse_date(val), [f], f"'{ev}' read as {val}")
        elif f in ("subtotal", "discount", "tax", "total"):
            pe = parse_amount(ev)
            if pe is not None:
                check("evidence_match", close(abs(pe), abs(parse_amount(val))), [f], f"'{ev}' read as {val}")
        if kind == "digital" and f != "currency":          # currency is inferred from symbols like "$" or "Rs."
            if f in ("subtotal", "discount", "tax", "total"):
                found = round(abs(parse_amount(val)), 2) in numbers
            else:
                found = _norm(str(ev)) in _norm(text_layer)
            check("in_document", found, [f], "not found in the PDF text")

    bad_lines = [i + 1 for i, it in enumerate(items)
                 if None not in (it.get("quantity"), it.get("unit_price"), it.get("amount"))
                 and not close(it["quantity"] * it["unit_price"], it["amount"])]
    if items:
        check("line_math", not bad_lines, ["line_items"], f"lines {bad_lines}" if bad_lines else "")
        if kind == "digital":
            missing = [i + 1 for i, it in enumerate(items) if it.get("amount") is not None
                       and round(abs(it["amount"]), 2) not in numbers]
            check("in_document", not missing, ["line_items"], f"line amounts {missing} not in PDF text" if missing else "")
        amounts = [it.get("amount") for it in items]
        if sub is not None and None not in amounts:
            s = round(sum(amounts), 2)
            check("items_sum", close(s, sub), ["line_items", "subtotal"], f"lines add to {s}, subtotal {sub}")
    else:
        check("required", False, ["line_items"], "no line items")
    if None not in (sub, tax, total):
        expect = round(sub - disc + tax, 2)
        check("total_math", close(expect, total), ["subtotal", "discount", "tax", "total"],
              f"{sub} - {disc} + {tax} = {expect}, printed {total}")
    if None not in (sub, tax) and sub - disc > 0:
        rate = tax / (sub - disc)
        check("tax_rate", 0 <= rate <= max_tax_rate, ["tax"], f"{rate:.1%} of taxable amount")
    cur = value_of(ext, "currency")
    if cur:
        check("currency", str(cur).upper() in CURRENCIES, ["currency"], str(cur))
    if vendors and value_of(ext, "vendor"):
        exact, closest, sim = match_vendor(str(value_of(ext, "vendor")), vendors)
        hint = f"closest: {closest['name']}" if closest and sim >= 0.6 else "new supplier?"
        check("vendor_known", exact is not None, ["vendor"], "" if exact else f"not in vendor master ({hint})")
        if exact:
            num = value_of(ext, "invoice_number")
            if num and exact.get("invoice_number_pattern"):
                check("number_format", bool(re.fullmatch(exact["invoice_number_pattern"], str(num).strip())),
                      ["invoice_number"], f"expected format {exact['invoice_number_pattern']}")
            if cur and exact.get("currency"):
                check("currency_match", str(cur).upper() == exact["currency"], ["currency"], f"{exact['name']} bills in {exact['currency']}")
    for f in ext.get("uncertain_fields") or []:
        if f in reasons:
            check("model_uncertain", False, [f], "flagged by the model as hard to read")

    fields = {f: {"status": "review" if reasons[f] else "ok", "reasons": sorted(set(reasons[f]))} for f in ALL_FIELDS}
    return {"checks": checks, "fields": fields}
