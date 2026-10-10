# Folio: Invoice Extraction You Can Audit

An AI document pipeline that reads invoices (digital PDFs, scans and phone photos) and turns them into structured data for accounting. Every extracted field is checked in code before anyone trusts it, and anything the checks can't confirm goes to a person on a review screen built around the document itself.

![Folio results](https://raw.githubusercontent.com/anjeesanjeet/folio-invoice-extraction/main/outputs/thumbnail.png)

## The problem

Finance teams still key in invoices by hand. AI can read them in seconds, but an AI that is right 97% of the time is not good enough on its own: one wrong digit in a total, a misread date or an invented line item flows straight into the books, and nobody notices until a payment or an audit goes wrong.

The real requirements:

- Read every kind of invoice: different layouts, labels, currencies and number formats, and poor-quality scans.
- Never let a wrong value through unnoticed. A flagged error costs seconds; a silent one costs money.
- Keep people in the loop only where they add value, not on every document.
- Prove the error rate with measurements, not a demo.

## What I built

Folio runs every document through the same pipeline:

- **Ingest:** digital PDFs keep their text layer; scans and photos are treated as images.
- **Extract:** a vision model reads the page and returns every field (vendor, number, dates, currency, subtotal, discount, tax, total and line items) together with the exact text it read each value from.
- **Check in code:** fourteen checks run on every field. Line items must multiply and add up, subtotal minus discount plus tax must equal the total, dates must parse and make sense, every value must match the text it came from, on digital PDFs every value must actually appear in the document's text layer, and the vendor must match the supplier list, with that supplier's usual invoice-number format and currency. Duplicate invoices are flagged before they can be paid twice.
- **Route:** if every field passes, the invoice is auto-approved. If any field is in doubt, only that field is highlighted for a person, with the reason shown.
- **Review and export:** a review screen shows the invoice next to its fields; people correct values and approve. Approved data exports to Excel and CSV, with human corrections taking priority.

The key design decision: the model reads, code decides. A model's confidence is not evidence; arithmetic and the document's own text are.

## How I measured it

I built a labelled test set of 40 invoices from nine vendors in four countries: three layouts, US, Indian and European date and number formats (including 1,23,456.00 and 1.234,50), optional discounts and due dates, and different labels for the same field. Twelve were turned into ordinary scans and ten into poor-quality scans: low resolution, tilted, blurred and heavily compressed. Two contain a genuine vendor arithmetic mistake: the printed total doesn't add up.

Every field of every invoice is scored against the correct value and sorted into outcomes: correct and passed, correct but sent to review, wrong but caught, and wrong and missed. The last one, the silent error, is the number that matters.

A model that makes no mistakes on a test set proves nothing about the checks, so a second test injects realistic reading mistakes (wrong digits, decimal shifts, dropped lines, misread dates and names) into the model's own extractions, one at a time, and counts how many the checks catch.

Measured results are in the evaluation and stress-test reports in the outputs folder.

## Architecture and stack

- **Models:** Claude (default Haiku 4.5) or OpenAI vision, with structured output through a forced tool call
- **Documents:** pypdfium2 for rendering, pdfplumber for the text layer, Pillow for scans
- **Backend:** Python, FastAPI, SQLite with a step-by-step log for every document
- **Output:** Excel (invoices and line items sheets) and CSV
- **Evaluation:** labelled synthetic invoice generator with ground truth, field-level scoring
- **Visuals:** review screen, results dashboard, flowcharts generated from the code
- **Quality:** offline tests covering every check with a scripted model

## Run it yourself

Setup, commands, the full list of checks and the API are in the [setup guide](SETUP.md).
