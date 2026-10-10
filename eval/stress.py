"""Stress test: do the checks catch the model's mistakes?

A perfect extraction run can't show that, so this injects realistic reading mistakes into each document's
extraction and counts how many the checks flag. It is offline and free: no model calls.

Base extractions come from your last `python -m eval.run_eval` (the real model output); documents without
one fall back to the ground truth. Each mistake is applied on its own to every document where it applies.

Two kinds of mistake:
  slip    the model read the text right but wrote the value wrong (evidence stays correct)
  misread the model read the text wrong, so value and evidence are both wrong (the hard case)

Usage:  python -m eval.stress
Writes outputs/stress_results.json (dashboard) and outputs/stress_report.md.
"""
from __future__ import annotations

import copy
import json
import random
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from app.config import get_settings
from app.generate import printed_extraction
from app.ingest import load
from app.validate import parse_date, validate


def _bump_digit(s: str, rng: random.Random) -> str:
    """Changes one digit, as OCR-style misreads do (3->8, 1->7, 6->5...)."""
    confusions = {"0": "8", "1": "7", "3": "8", "5": "6", "6": "5", "7": "1", "8": "3", "9": "4", "2": "7", "4": "9"}
    idx = [i for i, c in enumerate(s) if c.isdigit()]
    i = rng.choice(idx[:-2] if len(idx) > 3 else idx)
    return s[:i] + confusions[s[i]] + s[i + 1:]


def _num(v) -> float:
    return float(v) if v is not None else 0.0


def _set(ext, f, value, evidence=None):
    ext[f] = {"value": value, "evidence": ext.get(f, {}).get("evidence") if evidence is None else evidence}


def m_total_slip(ext, t, rng):
    v = _num(ext["total"]["value"])
    _set(ext, "total", round(v + rng.choice([9, 90, 0.9]), 2))
    return "total"


def m_total_misread(ext, t, rng):
    v = _num(ext["total"]["value"])
    nv = float(_bump_digit(f"{v:.2f}", rng))
    _set(ext, "total", nv, (ext["total"].get("evidence") or "").replace(f"{v:,.2f}", f"{nv:,.2f}") or f"{nv:,.2f}")
    return "total"


def m_decimal_shift(ext, t, rng):
    v = _num(ext["subtotal"]["value"])
    _set(ext, "subtotal", round(v * 10, 2), f"{v * 10:,.2f}")
    return "subtotal"


def m_tax_misread(ext, t, rng):
    v = _num(ext["tax"]["value"])
    nv = float(_bump_digit(f"{v:.2f}", rng))
    _set(ext, "tax", nv, f"{nv:,.2f}")
    return "tax"


def m_line_misread(ext, t, rng):
    it = ext["line_items"][rng.randrange(len(ext["line_items"]))]
    it["amount"] = float(_bump_digit(f"{_num(it['amount']):.2f}", rng))
    return "line_items"


def m_line_dropped(ext, t, rng):
    if len(ext["line_items"]) < 2:
        return None
    ext["line_items"].pop(rng.randrange(len(ext["line_items"])))
    return "line_items"


def m_discount_missed(ext, t, rng):
    if not _num((ext.get("discount") or {}).get("value")):
        return None
    _set(ext, "discount", None, "")
    ext["discount"]["evidence"] = None
    return "discount"


def m_date_slip(ext, t, rng):
    d = parse_date(ext["invoice_date"]["value"])
    _set(ext, "invoice_date", (d + timedelta(days=rng.choice([-2, -1, 1, 2]))).isoformat())
    return "invoice_date"


def m_date_misread(ext, t, rng):
    d = parse_date(ext["invoice_date"]["value"])
    nd = d + timedelta(days=rng.choice([-2, -1, 1, 2]))
    ev = ext["invoice_date"].get("evidence") or ""
    new_ev = re.sub(rf"\b0?{d.day}\b", str(nd.day) if nd.month == d.month else f"{nd.day:02d}", ev, count=1)
    _set(ext, "invoice_date", nd.isoformat(), new_ev if new_ev != ev else nd.isoformat())
    return "invoice_date"


def m_number_misread(ext, t, rng):
    v = str(ext["invoice_number"]["value"])
    if not any(c.isdigit() for c in v):
        return None
    nv = _bump_digit(v, rng)
    _set(ext, "invoice_number", nv, nv)
    return "invoice_number"


def m_vendor_misread(ext, t, rng):
    v = str(ext["vendor"]["value"])
    nv = v.replace("a", "o", 1) if "a" in v else v + "s"
    _set(ext, "vendor", nv, nv)
    return "vendor"


MUTATIONS = [
    ("Total: value slip", "slip", m_total_slip),
    ("Total: digit misread", "misread", m_total_misread),
    ("Subtotal: decimal shift", "misread", m_decimal_shift),
    ("Tax: digit misread", "misread", m_tax_misread),
    ("Line amount: digit misread", "misread", m_line_misread),
    ("Line item dropped", "misread", m_line_dropped),
    ("Discount missed", "misread", m_discount_missed),
    ("Invoice date: conversion slip", "slip", m_date_slip),
    ("Invoice date: misread", "misread", m_date_misread),
    ("Invoice number: digit misread", "misread", m_number_misread),
    ("Vendor name: misread", "misread", m_vendor_misread),
]


def base_extractions(s) -> dict:
    db = s.outputs_dir / "eval_work" / "eval.db"
    out = {}
    if db.exists():
        conn = sqlite3.connect(str(db))
        for fname, ext in conn.execute("SELECT filename, extracted FROM documents WHERE extracted IS NOT NULL"):
            out[fname] = json.loads(ext)
        conn.close()
    return out


def run() -> dict:
    s = get_settings()
    truths = json.loads((s.samples_dir / "ground_truth.json").read_text(encoding="utf-8"))
    bases = base_extractions(s)
    rng = random.Random(11)
    vendors = s.vendors()
    rows, used_model = [], 0
    for t in truths:
        if t["trap"]:
            continue                                    # traps already fail total_math; they'd inflate the score
        doc = load(s.samples_dir / t["file"])
        base = bases.get(t["file"])
        used_model += base is not None
        base = base or printed_extraction(t)
        if any(v["status"] != "ok" for v in validate(base, doc.kind, doc.text, vendors=vendors, sharpness=doc.sharpness, min_sharpness=s.min_sharpness)["fields"].values()):
            continue                                    # only start from extractions that passed cleanly
        for name, kind, fn in MUTATIONS:
            ext = copy.deepcopy(base)
            field = fn(ext, t, rng)
            if field is None:
                continue
            res = validate(ext, doc.kind, doc.text, vendors=vendors, sharpness=doc.sharpness, min_sharpness=s.min_sharpness)
            caught = res["fields"][field]["status"] != "ok"
            by = sorted({c["name"] for c in res["checks"] if not c["passed"] and field in c["fields"]})
            rows.append({"file": t["file"], "doc_kind": t["kind"], "mutation": name, "type": kind, "field": field,
                         "caught": caught, "caught_by": by})

    def agg(items):
        return {"n": len(items), "caught": sum(r["caught"] for r in items),
                "rate": round(sum(r["caught"] for r in items) / len(items), 4) if items else None}

    by_mut, by_kind = defaultdict(list), defaultdict(list)
    for r in rows:
        by_mut[r["mutation"]].append(r)
        by_kind["digital" if r["doc_kind"] == "digital" else "scan"].append(r)
    payload = {"documents": len({r["file"] for r in rows}), "base_from_model": used_model, "overall": agg(rows),
               "by_kind": {k: agg(v) for k, v in by_kind.items()},
               "by_mutation": [{"mutation": m, "type": v[0]["type"], **agg(v),
                                "digital": agg([r for r in v if r["doc_kind"] == "digital"]),
                                "scan": agg([r for r in v if r["doc_kind"] != "digital"]),
                                "checks": sorted({c for r in v for c in r["caught_by"]})} for m, v in by_mut.items()],
               "rows": rows}
    s.outputs_dir.mkdir(parents=True, exist_ok=True)
    (s.outputs_dir / "stress_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (s.outputs_dir / "stress_report.md").write_text(report(payload), encoding="utf-8")
    return payload


def report(p) -> str:
    pct = lambda a: "n/a" if a["rate"] is None else f"{a['rate']:.0%} ({a['caught']}/{a['n']})"
    lines = ["# Folio stress test", "",
             f"{p['overall']['n']} realistic mistakes injected into {p['documents']} documents "
             f"({p['base_from_model']} real model extractions). Caught overall: **{pct(p['overall'])}**.", "",
             f"Digital PDFs: {pct(p['by_kind'].get('digital', {'rate': None}))}. "
             f"Scans: {pct(p['by_kind'].get('scan', {'rate': None}))}.", "",
             "| Mistake | Type | Digital PDFs | Scans | Caught by |", "|---|---|---|---|---|"]
    lines += [f"| {m['mutation']} | {m['type']} | {pct(m['digital'])} | {pct(m['scan'])} | {', '.join(m['checks'])} |"
              for m in p["by_mutation"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    p = run()
    print(report(p))
    print("Saved outputs/stress_results.json and outputs/stress_report.md")