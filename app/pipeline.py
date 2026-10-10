"""Processes one document end to end and records every step (used for metrics and the trace flowchart)."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from app import extract as extractor
from app.config import Settings
from app.db import connect, events_for, get_doc, log_event, now_iso, update_doc
from app.extract import ALL_FIELDS
from app.ingest import load
from app.llm import BaseProvider
from app.validate import validate

# The pipeline's steps, in order. The architecture flowchart is generated from this list.
STEPS = [
    ("ingest", "Read the file", "PDF text layer kept; scans rendered and graded for image quality"),
    ("extract", "Extract fields with a vision model", "every value returned with the exact text it came from"),
    ("validate", "Check every field in code", "arithmetic, dates, evidence, PDF text, vendor master, duplicates, image quality"),
    ("route", "Route the document", "all checks pass: auto-approved; any doubt: human review"),
    ("export", "Export", "CSV and Excel; human corrections override extraction"),
]


class Pipeline:
    def __init__(self, settings: Settings, provider: BaseProvider | None, db_path: Path | str | None = None,
                 storage_dir: Path | None = None):
        self.s, self.provider = settings, provider
        self.db_path = Path(db_path or settings.db_path)
        self.storage = Path(storage_dir or settings.storage_dir)

    def add(self, src: Path, filename: str | None = None) -> int:
        """Copies a file into storage and registers it."""
        conn = connect(self.db_path)
        try:
            ts = now_iso()
            cur = conn.execute("INSERT INTO documents (filename, path, created_at, updated_at) VALUES (?,?,?,?)",
                               (filename or src.name, "", ts, ts))
            doc_id = cur.lastrowid
            self.storage.mkdir(parents=True, exist_ok=True)
            dest = self.storage / f"{doc_id:05d}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
            update_doc(conn, doc_id, path=str(dest))
            return doc_id
        finally:
            conn.close()

    def page_path(self, doc_id: int, page: int = 1) -> Path:
        return self.storage / f"{doc_id:05d}_p{page}.png"

    def process(self, doc_id: int) -> dict:
        conn = connect(self.db_path)
        t_start, cost = time.perf_counter(), 0.0
        try:
            doc = get_doc(conn, doc_id)
            if not doc:
                raise ValueError(f"Document {doc_id} not found")
            conn.execute("DELETE FROM events WHERE doc_id = ?", (doc_id,))
            update_doc(conn, doc_id, status="processing", error=None, corrected=None, reviewed_at=None)
            try:
                t = time.perf_counter()
                d = load(Path(doc["path"]), self.s.max_pages, self.s.render_scale)
                for i, png in enumerate(d.pages, 1):
                    self.page_path(doc_id, i).write_bytes(png)
                update_doc(conn, doc_id, kind=d.kind, pages=len(d.pages))
                log_event(conn, doc_id, "ingest", "ok", f"{d.kind}, {len(d.pages)} page(s)"
                          + (f", {len(d.text)} chars of text" if d.text else "")
                          + (f", sharpness {d.sharpness:.0f}" if d.sharpness is not None else ""), (time.perf_counter() - t) * 1000)

                t = time.perf_counter()
                res = extractor.extract(self.provider, d.pages, d.text)
                cost += res.cost_usd
                ext = res.data
                if not ext:
                    raise RuntimeError("The model returned no data")
                n_items = len(ext.get("line_items") or [])
                log_event(conn, doc_id, "extract", "ok", f"{n_items} line items, {res.input_tokens + res.output_tokens} tokens",
                          (time.perf_counter() - t) * 1000, res.cost_usd)

                t = time.perf_counter()
                val = validate(ext, d.kind, d.text, self.s.max_tax_rate, self.s.vendors(), d.sharpness, self.s.min_sharpness)
                dup = self._duplicate_of(conn, doc_id, ext)
                val["checks"].append({"name": "duplicate", "passed": dup is None, "fields": ["invoice_number"],
                                      "detail": f"same vendor and number as document {dup}" if dup else ""})
                if dup:
                    val["fields"]["invoice_number"]["status"] = "review"
                    val["fields"]["invoice_number"]["reasons"].append(f"duplicate: same vendor and number as document {dup}")
                failed = [c for c in val["checks"] if not c["passed"]]
                log_event(conn, doc_id, "validate", "ok" if not failed else "warning",
                          f"{len(val['checks']) - len(failed)} of {len(val['checks'])} checks passed"
                          + (": " + ", ".join(sorted({c['name'] for c in failed})) if failed else ""),
                          (time.perf_counter() - t) * 1000)

                flagged = [f for f in ALL_FIELDS if val["fields"][f]["status"] != "ok"]
                status = "needs_review" if flagged else "auto_approved"
                log_event(conn, doc_id, "route", "ok" if not flagged else "warning",
                          "auto-approved" if not flagged else f"{len(flagged)} field(s) to review: {', '.join(flagged)}")
                update_doc(conn, doc_id, extracted=ext, validation=val, status=status)
            except Exception as exc:
                log_event(conn, doc_id, "error", "failed", f"{type(exc).__name__}: {exc}")
                update_doc(conn, doc_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
            update_doc(conn, doc_id, cost_usd=round(cost, 6), duration_ms=round((time.perf_counter() - t_start) * 1000, 1))
            return self.summary(conn, doc_id)
        finally:
            conn.close()

    @staticmethod
    def _duplicate_of(conn, doc_id: int, ext: dict) -> int | None:
        """Another non-rejected document with the same vendor and invoice number (a classic double payment)."""
        import json
        import re as _re
        norm = lambda x: _re.sub(r"[^a-z0-9]", "", str(x or "").lower())
        v, n = (ext.get("vendor") or {}).get("value"), (ext.get("invoice_number") or {}).get("value")
        if not v or not n:
            return None
        for row in conn.execute("SELECT id, extracted, corrected FROM documents WHERE id != ? AND extracted IS NOT NULL "
                                "AND status != 'rejected'", (doc_id,)):
            other, corr = json.loads(row["extracted"]), json.loads(row["corrected"] or "{}")
            ov = corr.get("vendor", (other.get("vendor") or {}).get("value"))
            on = corr.get("invoice_number", (other.get("invoice_number") or {}).get("value"))
            if norm(ov) == norm(v) and norm(on) == norm(n):
                return row["id"]
        return None

    def review(self, doc_id: int, decision: str, corrections: dict | None = None) -> dict:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        conn = connect(self.db_path)
        try:
            if not get_doc(conn, doc_id):
                raise ValueError(f"Document {doc_id} not found")
            update_doc(conn, doc_id, status="approved" if decision == "approve" else "rejected",
                       corrected=corrections or {}, reviewed_at=now_iso())
            n = len(corrections or {})
            log_event(conn, doc_id, "human_review", "ok", f"{decision}d" + (f" with {n} correction(s)" if n else ""))
            return self.summary(conn, doc_id)
        finally:
            conn.close()

    @staticmethod
    def summary(conn, doc_id: int) -> dict:
        doc = get_doc(conn, doc_id)
        doc["events"] = events_for(conn, doc_id)
        doc["final"] = final_values(doc)
        return doc


def final_values(doc: dict) -> dict:
    """Extracted values with any human corrections applied on top."""
    ext, corr = doc.get("extracted") or {}, doc.get("corrected") or {}
    out = {}
    for f in ALL_FIELDS:
        if f == "line_items":
            out[f] = corr.get(f, ext.get(f) or [])
        else:
            v = ext.get(f)
            out[f] = corr.get(f, v.get("value") if isinstance(v, dict) else v)
    return out