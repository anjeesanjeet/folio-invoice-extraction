"""Evaluation: processes the labelled sample set and scores every field against ground truth.

The key metric is the SILENT ERROR: a wrong value that passed every check and would flow into the accounts
system unnoticed. A wrong value that was flagged for review is a CAUGHT error; a correct value that was
flagged is a FALSE ALARM (costs a few seconds of human time, not money).

Usage:
    python -m eval.run_eval              # all samples (generated on first run)
    python -m eval.run_eval --limit 8    # quick check
Writes outputs/eval_results.json (dashboard + thumbnail) and outputs/eval_report.md (case study).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.config import get_settings
from app.extract import ALL_FIELDS
from app.generate import generate
from app.llm import ProviderConfigError, get_provider
from app.pipeline import Pipeline, final_values
from app.validate import close, parse_amount, parse_date

STATES = ("ok", "anomaly", "false_alarm", "caught", "silent")
ARITH = {"subtotal", "discount", "tax", "total"}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def field_correct(f: str, got, want) -> bool:
    if f == "line_items":
        got, want = got or [], want or []
        if len(got) != len(want):
            return False
        key = lambda it: (parse_amount(it.get("amount")) or 0)
        return all(close(parse_amount(g.get("amount")), w["amount"]) and close(parse_amount(g.get("quantity")), w["quantity"])
                   for g, w in zip(sorted(got, key=key), sorted(want, key=key)))
    if f in ("subtotal", "discount", "tax", "total"):
        g, w = parse_amount(got) or 0.0, want or 0.0          # a missing discount equals a zero discount
        return close(abs(g), abs(w)) if (w or g) else True
    if f in ("invoice_date", "due_date"):
        return (parse_date(got) == parse_date(want)) if want else got in (None, "")
    if f == "vendor":
        return SequenceMatcher(None, _norm(got), _norm(want)).ratio() >= 0.9
    return _norm(got) == _norm(want)


def score(doc: dict, truth: dict) -> dict:
    vals = final_values(doc)
    fields = ((doc.get("validation") or {}).get("fields")) or {}
    cells = {}
    for f in ALL_FIELDS:
        ok = field_correct(f, vals.get(f), truth.get(f))
        flagged = fields.get(f, {}).get("status", "review") != "ok"
        if ok and flagged and truth.get("trap") and f in ARITH:
            cells[f] = "anomaly"                 # the invoice itself doesn't add up: flagging it is correct
        else:
            cells[f] = ("false_alarm" if flagged else "ok") if ok else ("caught" if flagged else "silent")
    return cells


def run(provider_name: str | None, limit: int | None) -> dict:
    base = get_settings()
    truth_path = base.samples_dir / "ground_truth.json"
    if not truth_path.exists() or not any(t["kind"] == "hard_scan" for t in json.loads(truth_path.read_text(encoding="utf-8"))):
        print("Generating the labelled sample set (40 invoices)...")
        generate(base.samples_dir)
    truths = json.loads(truth_path.read_text(encoding="utf-8"))[:limit]
    provider = get_provider(base, provider_name)
    work = base.outputs_dir / "eval_work"
    shutil.rmtree(work, ignore_errors=True)
    s = copy.copy(base)
    pipe = Pipeline(s, provider, db_path=work / "eval.db", storage_dir=work / "store")

    print(f"\nEvaluating {len(truths)} documents with {provider.name}:{provider.model}\n")
    docs = []
    for i, t in enumerate(truths, 1):
        out = pipe.process(pipe.add(base.samples_dir / t["file"]))
        cells = score(out, t) if out["status"] != "failed" else {f: "silent" for f in ALL_FIELDS}
        rec = {"file": t["file"], "kind": t["kind"], "trap": t["trap"], "country": t["country"], "layout": t["layout"],
               "status": out["status"], "cells": cells, "cost_usd": out["cost_usd"], "duration_ms": out["duration_ms"],
               "error": out.get("error"),
               "failed_checks": sorted({c["name"] for c in (out.get("validation") or {}).get("checks", []) if not c["passed"]})}
        docs.append(rec)
        tally = {k: sum(1 for v in cells.values() if v == k) for k in STATES}
        print(f"  [{i:>2}/{len(truths)}] {t['file']:<11} {t['kind']:<7} {out['status']:<14} "
              f"ok {tally['ok']:>2}  anomaly {tally['anomaly']}  flagged-ok {tally['false_alarm']}  caught {tally['caught']}  SILENT {tally['silent']}"
              f"  {out['duration_ms'] / 1000:.1f}s ${out['cost_usd']:.4f}" + (f"  {out['error']}" if out.get("error") else ""))

    payload = {"meta": {"provider": provider.name, "model": provider.model, "documents": len(docs), "fields": ALL_FIELDS,
                        "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()},
               "summary": summarize(docs), "by_field": by_field(docs), "by_kind": by_group(docs, "kind"), "documents": docs}
    base.outputs_dir.mkdir(parents=True, exist_ok=True)
    base.eval_results_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (base.outputs_dir / "eval_report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def _rate(a, b):
    return round(a / b, 4) if b else None


def _percentile(vals, pct):
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 1)


def summarize(docs: list[dict]) -> dict:
    cells = [c for d in docs for c in d["cells"].values()]
    n = len(cells)
    count = {k: cells.count(k) for k in STATES}
    correct = count["ok"] + count["false_alarm"] + count["anomaly"]
    errors = count["caught"] + count["silent"]
    normal = [d for d in docs if not d["trap"]]
    auto = [d for d in normal if d["status"] == "auto_approved"]
    traps = [d for d in docs if d["trap"]]
    durations = [d["duration_ms"] for d in docs]
    return {
        "documents": len(docs), "fields": n, **{f"fields_{k}": v for k, v in count.items()},
        "field_accuracy": _rate(correct, n),
        "silent_errors": count["silent"], "silent_error_rate": _rate(count["silent"], n),
        "error_catch_rate": _rate(count["caught"], errors),
        "fields_flagged_rate": _rate(count["false_alarm"] + count["caught"] + count["anomaly"], n),
        "false_alarm_rate": _rate(count["false_alarm"], n),
        "straight_through_rate": _rate(len(auto), len(normal)),
        "auto_approved_fully_correct": _rate(sum(1 for d in auto if all(v == "ok" for v in d["cells"].values())), len(auto)),
        "traps": len(traps), "traps_caught": sum(1 for d in traps if d["status"] == "needs_review"),
        "failed_documents": sum(1 for d in docs if d["status"] == "failed"),
        "cost_per_doc_usd": round(sum(d["cost_usd"] for d in docs) / len(docs), 5) if docs else None,
        "total_cost_usd": round(sum(d["cost_usd"] for d in docs), 4),
        "duration_avg_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "duration_p95_ms": _percentile(durations, 95),
    }


def by_field(docs):
    out = []
    for f in ALL_FIELDS:
        states = [d["cells"][f] for d in docs]
        out.append({"field": f, **{k: states.count(k) for k in STATES},
                    "accuracy": _rate(states.count("ok") + states.count("false_alarm") + states.count("anomaly"), len(states))})
    return out


def by_group(docs, key):
    g = defaultdict(list)
    for d in docs:
        g[d[key]].append(d)
    return [{"group": k, "documents": len(v), **{x: y for x, y in summarize(v).items()
                                                  if x in ("field_accuracy", "silent_errors", "straight_through_rate")}}
            for k, v in g.items()]


def render_report(p: dict) -> str:
    s, m = p["summary"], p["meta"]
    pct = lambda v: "n/a" if v is None else f"{v:.1%}"
    lines = ["# Folio evaluation report", "",
             f"Model: `{m['provider']}:{m['model']}`  |  Documents: {m['documents']}  |  Run: {m['run_at']}", "",
             "| Metric | Result |", "|---|---|",
             f"| Silent errors (wrong and not flagged) | {s['silent_errors']} of {s['fields']} fields ({pct(s['silent_error_rate'])}) |",
             f"| Field accuracy (before review) | {pct(s['field_accuracy'])} |",
             f"| Extraction errors caught by checks | {pct(s['error_catch_rate'])} ({s['fields_caught']} caught) |",
             f"| Fields sent to review | {pct(s['fields_flagged_rate'])} |",
             f"| Correct fields flagged without need (false alarms) | {pct(s['false_alarm_rate'])} |",
             f"| Documents auto-approved | {pct(s['straight_through_rate'])} |",
             f"| Auto-approved documents fully correct | {pct(s['auto_approved_fully_correct'])} |",
             f"| Vendor arithmetic errors caught | {s['traps_caught']} of {s['traps']} |",
             f"| Cost per document | ${s['cost_per_doc_usd']:.4f} |",
             f"| Time per document, avg / p95 | {s['duration_avg_ms']/1000:.1f}s / {s['duration_p95_ms']/1000:.1f}s |",
             "", "## By document type", "", "| Type | Documents | Field accuracy | Silent errors | Auto-approved |", "|---|---|---|---|---|"]
    lines += [f"| {g['group']} | {g['documents']} | {pct(g['field_accuracy'])} | {g['silent_errors']} | {pct(g['straight_through_rate'])} |"
              for g in p["by_kind"]]
    lines += ["", "## By field", "", "| Field | Accuracy | Caught | Silent | False alarms |", "|---|---|---|---|---|"]
    lines += [f"| {f['field']} | {pct(f['accuracy'])} | {f['caught']} | {f['silent']} | {f['false_alarm']} |" for f in p["by_field"]]
    silent = [(d["file"], f) for d in p["documents"] for f, v in d["cells"].items() if v == "silent"]
    lines += ["", "## Silent errors", ""] + ([f"- {a}: {b}" for a, b in silent] or ["None."])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate Folio against ground truth.")
    ap.add_argument("--provider", choices=["anthropic", "openai"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    try:
        p = run(args.provider, args.limit)
    except ProviderConfigError as exc:
        sys.exit(f"Configuration error: {exc}")
    s = p["summary"]
    print(f"\nSilent errors {s['silent_errors']}/{s['fields']} | field accuracy {s['field_accuracy']:.1%} | "
          f"auto-approved {s['straight_through_rate']:.0%} | ${s['cost_per_doc_usd']:.4f}/doc")
    print("Saved outputs/eval_results.json and outputs/eval_report.md")


if __name__ == "__main__":
    main()
