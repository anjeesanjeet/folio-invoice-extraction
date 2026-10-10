import copy
from datetime import date

from app.ingest import load
from app.pipeline import Pipeline
from app.validate import parse_amount, parse_date, validate
from eval.run_eval import score, summarize
from app.generate import vendor_master
from tests.conftest import ScriptedProvider, perfect_extraction


def digital(samples):
    d, truth = samples
    t = next(x for x in truth if x["kind"] == "digital" and not x["trap"])
    return d, t


def flagged(res):
    return {f for f, v in res["fields"].items() if v["status"] != "ok"}


def test_parse_amount_formats():
    assert parse_amount("$1,234.50") == 1234.5
    assert parse_amount("1.234,50 EUR") == 1234.5
    assert parse_amount("Rs. 1,23,456.00") == 123456.0
    assert parse_amount("12,50") == 12.5
    assert parse_amount("-45.10") == -45.1 and parse_amount("n/a") is None


def test_parse_date_formats():
    assert parse_date("26-08-2026") == parse_date("26.08.2026") == parse_date("August 26, 2026") == date(2026, 8, 26)
    assert parse_date("08/26/2026") == date(2026, 8, 26) and parse_date("26 Aug 2026") == date(2026, 8, 26)


def test_correct_extraction_passes_every_check(samples):
    d, truth = samples
    for t in truth:
        if t["trap"]:
            continue
        doc = load(d / t["file"])
        assert not flagged(validate(perfect_extraction(t), doc.kind, doc.text, vendors=vendor_master())), t["file"]


def test_trap_invoice_is_flagged(samples):
    d, truth = samples
    t = next(x for x in truth if x["trap"])
    doc = load(d / t["file"])
    res = validate(perfect_extraction(t), doc.kind, doc.text)
    assert {"subtotal", "tax", "total"} <= flagged(res)
    doc_rec = {"extracted": perfect_extraction(t), "validation": res}
    assert score(doc_rec, t)["total"] == "anomaly"


def test_misread_total_is_caught_on_digital(samples):
    d, t = digital(samples)
    ext = perfect_extraction(t)
    ext["total"]["value"] = round(t["total"] + 9, 2)            # model slip: wrong digit
    doc = load(d / t["file"])
    res = validate(ext, doc.kind, doc.text)
    assert "total" in flagged(res)
    names = {c["name"] for c in res["checks"] if not c["passed"]}
    assert {"in_document", "total_math", "evidence_match"} <= names


def test_invented_vendor_is_caught_on_digital(samples):
    d, t = digital(samples)
    ext = perfect_extraction(t)
    ext["vendor"] = {"value": "Globex Corporation", "evidence": "Globex Corporation"}
    doc = load(d / t["file"])
    assert "vendor" in flagged(validate(ext, doc.kind, doc.text))


def test_scan_line_item_slip_is_caught_by_arithmetic(samples):
    d, truth = samples
    t = next(x for x in truth if x["kind"] == "scan")
    ext = perfect_extraction(t)
    ext["line_items"][0]["amount"] += 10
    assert {"line_items", "subtotal"} <= flagged(validate(ext, "scan"))


def test_date_conversion_slip_is_caught(samples):
    _, t = digital(samples)
    ext = perfect_extraction(t)
    d = date.fromisoformat(t["invoice_date"])
    ext["invoice_date"]["value"] = date(d.year, d.month, min(d.day, 28) - 1).isoformat()
    assert "invoice_date" in flagged(validate(ext, "scan"))


def test_pipeline_review_export_and_scoring(samples, settings):
    d, t = digital(samples)
    good, bad = perfect_extraction(t), perfect_extraction(t)
    bad["total"]["value"] = round(t["total"] + 1, 2)
    pipe = Pipeline(settings, ScriptedProvider([good, bad]))
    a = pipe.process(pipe.add(d / t["file"]))
    assert a["status"] == "auto_approved" and a["kind"] == "digital" and a["cost_usd"] > 0
    assert [e["step"] for e in a["events"]] == ["ingest", "extract", "validate", "route"]
    assert all(v == "ok" for v in score(a, t).values())
    b = pipe.process(pipe.add(d / t["file"]))
    assert b["status"] == "needs_review" and score(b, t)["total"] == "caught"
    r = pipe.review(b["id"], "approve", {"total": t["total"]})
    assert r["status"] == "approved" and r["final"]["total"] == t["total"]
    from app.exporter import export
    csv_path, xlsx = export(settings.db_path, settings.outputs_dir)
    assert xlsx.exists() and csv_path.read_text(encoding="utf-8-sig").count("\n") == 3


def test_silent_error_is_counted(samples, settings):
    d, t = digital(samples)
    doc = {"extracted": perfect_extraction(t), "validation": {"fields": {f: {"status": "ok"} for f in t}}}
    doc["extracted"]["invoice_number"]["value"] = "WRONG-1"
    cells = score(doc, t)
    assert cells["invoice_number"] == "silent"
    s = summarize([{"file": "x", "kind": "digital", "trap": False, "status": "auto_approved", "cells": cells,
                    "cost_usd": 0.01, "duration_ms": 1000}])
    assert s["silent_errors"] == 1 and s["auto_approved_fully_correct"] == 0


def test_flowcharts(samples, settings):
    from app.flowchart import pipeline_mermaid, trace_mermaid
    d, t = digital(samples)
    pipe = Pipeline(settings, ScriptedProvider([perfect_extraction(t)]))
    did = pipe.process(pipe.add(d / t["file"]))["id"]
    assert "C_total_math" in pipeline_mermaid(settings)
    assert "validate" in trace_mermaid(settings, did)


def test_vendor_master_catches_misread_and_format(samples):
    d, truth = samples
    t = next(x for x in truth if x["kind"] != "digital")
    ext = perfect_extraction(t)
    ext["vendor"] = {"value": t["vendor"] + "s", "evidence": None}
    res = validate(ext, "scan", vendors=vendor_master())
    assert "vendor" in flagged(res) and "closest" in res["fields"]["vendor"]["reasons"][0]
    ext = perfect_extraction(t)
    ext["invoice_number"]["value"] = "X-" + ext["invoice_number"]["value"]
    assert "invoice_number" in flagged(validate(ext, "scan", vendors=vendor_master()))


def test_duplicate_invoice_is_flagged(samples, settings):
    d, t = digital(samples)
    pipe = Pipeline(settings, ScriptedProvider([perfect_extraction(t), perfect_extraction(t)]))
    first = pipe.process(pipe.add(d / t["file"]))
    second = pipe.process(pipe.add(d / t["file"]))
    assert first["status"] == "auto_approved" and second["status"] == "needs_review"
    assert any("duplicate" in r for r in second["validation"]["fields"]["invoice_number"]["reasons"])


def test_stress_runs_offline(samples, settings, monkeypatch):
    import eval.stress as st
    d, _ = samples
    settings.samples_dir = d
    monkeypatch.setattr(st, "get_settings", lambda: settings)
    p = st.run()
    assert p["overall"]["n"] > 50 and p["by_kind"]["digital"]["rate"] == 1.0


def test_poor_scan_goes_to_review(samples):
    d, truth = samples
    hard = next(x for x in truth if x["kind"] == "hard_scan")
    ok = next(x for x in truth if x["kind"] == "scan")
    dh, do = load(d / hard["file"]), load(d / ok["file"])
    assert dh.sharpness < 280 <= do.sharpness
    res = validate(perfect_extraction(hard), "scan", vendors=vendor_master(), sharpness=dh.sharpness, min_sharpness=280)
    assert all(v["status"] == "review" for v in res["fields"].values())
    res = validate(perfect_extraction(ok), "scan", vendors=vendor_master(), sharpness=do.sharpness, min_sharpness=280)
    assert not flagged(res)