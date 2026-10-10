"""Command line: process a folder or files, then export.

    python -m app.cli process data/samples            # every PDF/image in a folder
    python -m app.cli process invoice.pdf scan.jpg    # specific files
    python -m app.cli export                          # outputs/invoices.csv + invoices.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.exporter import export
from app.ingest import IMAGE_EXT
from app.llm import ProviderConfigError, get_provider
from app.pipeline import Pipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Folio command line")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("process", help="Process files or folders")
    pr.add_argument("paths", nargs="+")
    ex = sub.add_parser("export", help="Export approved documents to CSV and Excel")
    ex.add_argument("--include-unreviewed", action="store_true")
    args = ap.parse_args()
    s = get_settings()

    if args.cmd == "export":
        c, x = export(s.db_path, s.outputs_dir, args.include_unreviewed)
        print(f"Wrote {c} and {x}")
        return
    files = []
    for p in map(Path, args.paths):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXT | {".pdf"}) if p.is_dir() else [p]
    try:
        pipe = Pipeline(s, get_provider(s))
    except ProviderConfigError as exc:
        sys.exit(f"Configuration error: {exc}")
    print(f"\nProcessing {len(files)} documents with {s.llm_provider}:{s.model_name}\n")
    for f in files:
        out = pipe.process(pipe.add(f))
        flagged = [k for k, v in ((out.get("validation") or {}).get("fields") or {}).items() if v["status"] != "ok"]
        print(f"  {f.name:<24} {str(out.get('kind')):<8} {out['status']:<14} "
              f"{'review: ' + ', '.join(flagged) if flagged else ''}  {out['duration_ms'] / 1000:.1f}s ${out['cost_usd']:.4f}"
              + (f"  {out['error']}" if out.get("error") else ""))
    print(f"\nReview flagged documents at http://{s.host}:{s.port}/review, then run: python -m app.cli export")


if __name__ == "__main__":
    main()
