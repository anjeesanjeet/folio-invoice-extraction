"""Exports processed documents to CSV and Excel (invoices sheet + line items sheet)."""
from __future__ import annotations

import csv
from pathlib import Path

from app.db import connect, to_dict
from app.extract import SCALAR_FIELDS
from app.pipeline import final_values

HEAD = ["doc_id", "filename", "status"] + SCALAR_FIELDS + ["fields_flagged"]


def _rows(db_path: Path, include_unreviewed: bool):
    conn = connect(db_path)
    try:
        docs = [to_dict(r) for r in conn.execute("SELECT * FROM documents WHERE status != 'new' ORDER BY id")]
    finally:
        conn.close()
    keep = ("auto_approved", "approved") + (("needs_review",) if include_unreviewed else ())
    for d in docs:
        if d["status"] in keep:
            flagged = [f for f, v in ((d.get("validation") or {}).get("fields") or {}).items() if v["status"] != "ok"]
            yield d, final_values(d), flagged


def export(db_path: Path, out_dir: Path, include_unreviewed: bool = False) -> tuple[Path, Path]:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(_rows(db_path, include_unreviewed))
    csv_path, xlsx_path = out_dir / "invoices.csv", out_dir / "invoices.xlsx"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(HEAD)
        for d, v, fl in rows:
            w.writerow([d["id"], d["filename"], d["status"]] + [v.get(f) for f in SCALAR_FIELDS] + [", ".join(fl)])
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    ws.append(HEAD)
    li = wb.create_sheet("Line items")
    li.append(["doc_id", "invoice_number", "description", "quantity", "unit_price", "amount"])
    for d, v, fl in rows:
        ws.append([d["id"], d["filename"], d["status"]] + [v.get(f) for f in SCALAR_FIELDS] + [", ".join(fl)])
        for it in v.get("line_items") or []:
            li.append([d["id"], v.get("invoice_number"), it.get("description"), it.get("quantity"),
                       it.get("unit_price"), it.get("amount")])
    for sheet in (ws, li):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(40, max(10, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(xlsx_path)
    return csv_path, xlsx_path
