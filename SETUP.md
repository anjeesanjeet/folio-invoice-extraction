# Folio: setup and technical guide

Back to the [project overview](README.md).

## Quick start

Requires Python 3.10+. Commands are for Windows PowerShell; on macOS/Linux use `source .venv/bin/activate` and `cp`.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then add ANTHROPIC_API_KEY
python -m pytest -q           # 15 tests, no API key needed
python -m app.main            # open http://127.0.0.1:8200
```

Drop any invoice (PDF, scan or phone photo) on the review page. Try the samples in `data/samples`.

## Command line

```powershell
python -m app.cli process data/samples         # a whole folder
python -m app.cli process my_invoice.pdf       # one file
python -m app.cli export                       # outputs/invoices.csv + invoices.xlsx (approved only)
python -m app.cli export --include-unreviewed
```

## Evaluate

```powershell
python -m eval.run_eval
```

Processes the 40 labelled invoices in `data/samples` (18 digital PDFs, 12 ordinary scans, 10 poor-quality
scans, 2 with vendor arithmetic mistakes) on an isolated database and scores every field against `ground_truth.json`.

| Outcome | Meaning |
|---|---|
| correct, passed | right value, passed every check |
| correct, sent to review | right value, but a check couldn't confirm it (costs a few seconds of review) |
| wrong, caught | wrong value, flagged for a human |
| wrong, missed | **silent error**: wrong value that passed every check |
| vendor error, flagged | the invoice itself doesn't add up, and Folio flagged it (the correct outcome) |

Writes `outputs/eval_results.json` (dashboard and thumbnail) and `outputs/eval_report.md`.
To regenerate the samples and the vendor master: `python -m app.generate`.

## Stress test

```powershell
python -m eval.stress
```

Run it after the evaluation. It injects 11 kinds of realistic reading mistakes (wrong digits, decimal shifts,
dropped lines, misread dates and names) into the model's own extractions, one at a time, and measures how many
the checks catch, for digital PDFs and scans separately. Offline and free: no model calls.
Writes `outputs/stress_results.json` (dashboard) and `outputs/stress_report.md`.

## Export portfolio assets

```powershell
python -m playwright install chromium     # once
python -m scripts.export_assets
```

Creates `outputs/thumbnail.png` (1600 x 1200), `dashboard_full.png`, `review_page.png`,
`flowchart_pipeline.png`, `flowchart_trace.png` and `docs/architecture.md`.

## Validation checks

| Check | What it catches |
|---|---|
| required | missing vendor, number, date, currency or total |
| date_valid | unparseable or implausible dates; due date before invoice date |
| evidence_match | the value doesn't match the text the model says it read (conversion slips) |
| in_document | digital PDFs: the value isn't in the PDF's text layer (invented values) |
| line_math | quantity x unit price differs from the line amount |
| items_sum | line amounts don't add up to the subtotal |
| total_math | subtotal - discount + tax differs from the total |
| tax_rate | tax outside 0-30% of the taxable amount |
| currency | not a known ISO currency code |
| model_uncertain | the model marked the field as hard to read |
| vendor_known | vendor isn't an exact match in the vendor master (misread or new supplier) |
| number_format | invoice number doesn't fit that vendor's usual format |
| currency_match | currency differs from the one that vendor bills in |
| duplicate | same vendor and invoice number as an earlier document (double payment) |
| image_quality | scans: the image is too blurry or low-resolution to trust; the whole invoice goes to a person |

The image-quality threshold (`MIN_SHARPNESS` in `.env`, default 280) is calibrated on the sample set, where ordinary
scans score 370-500 and poor scans 175-190. For a real client, calibrate it on a sample of their own documents.

The vendor master is `config/vendors.json`: one entry per supplier with its name, aliases, invoice-number
pattern (a regular expression) and currency. Delete the file to switch these checks off.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | /api/documents | Upload and process a file (multipart `file`) |
| GET | /api/documents, /api/documents/{id} | List, full detail |
| GET | /api/documents/{id}/page/{n} | Page image |
| POST | /api/documents/{id}/reprocess | Read again |
| POST | /api/documents/{id}/review | Approve or reject, with corrections |
| GET | /api/export/xlsx, /api/export/csv | Download approved data |
| GET | /api/dashboard, /api/flowchart | Dashboard data, Mermaid diagrams |

Interactive docs at `/docs`.

## Project structure

```
app/
  config.py      settings from .env
  generate.py    labelled synthetic invoices (PDF + degraded scans) with ground truth
  ingest.py      PDF text layer and page images; images treated as scans
  llm.py         Claude / OpenAI vision with structured output
  extract.py     extraction schema and instructions
  validate.py    the checks, plus number and date parsing (1,23,456.00 / 1.234,50 / 26.08.2026)
  pipeline.py    orchestration, step log, human review
  exporter.py    CSV and Excel
  flowchart.py   generated Mermaid diagrams
  main.py        FastAPI app
  cli.py         command line
data/samples/    40 labelled invoices + ground_truth.json
config/          vendors.json (vendor master)
eval/            run_eval.py (accuracy), stress.py (injected mistakes)
static/          review, results and flowchart pages
scripts/         export_assets.py
tests/           offline tests with a scripted model
```