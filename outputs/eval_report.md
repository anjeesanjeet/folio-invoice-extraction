# Folio evaluation report

Model: `anthropic:claude-haiku-4-5-20251001`  |  Documents: 40  |  Run: 2026-10-10T21:01:08+00:00

| Metric | Result |
|---|---|
| Silent errors (wrong and not flagged) | 8 of 400 fields (2.0%) |
| Field accuracy (before review) | 89.5% |
| Extraction errors caught by checks | 81.0% (34 caught) |
| Fields sent to review | 14.5% |
| Correct fields flagged without need (false alarms) | 4.0% |
| Documents auto-approved | 73.7% |
| Auto-approved documents fully correct | 100.0% |
| Vendor arithmetic errors caught | 2 of 2 |
| Cost per document | $0.0059 |
| Time per document, avg / p95 | 5.0s / 5.9s |

## By document type

| Type | Documents | Field accuracy | Silent errors | Auto-approved |
|---|---|---|---|---|
| digital | 18 | 100.0% | 0 | 100.0% |
| scan | 12 | 100.0% | 0 | 100.0% |
| hard_scan | 10 | 58.0% | 8 | 0.0% |

## By field

| Field | Accuracy | Caught | Silent | False alarms |
|---|---|---|---|---|
| vendor | 100.0% | 0 | 0 | 0 |
| invoice_number | 80.0% | 7 | 1 | 1 |
| invoice_date | 87.5% | 2 | 3 | 0 |
| due_date | 90.0% | 2 | 2 | 0 |
| currency | 100.0% | 0 | 0 | 0 |
| subtotal | 85.0% | 6 | 0 | 3 |
| discount | 95.0% | 2 | 0 | 5 |
| tax | 85.0% | 6 | 0 | 1 |
| total | 97.5% | 1 | 0 | 6 |
| line_items | 75.0% | 8 | 2 | 0 |

## Silent errors

- INV031.jpg: invoice_number
- INV031.jpg: due_date
- INV033.jpg: invoice_date
- INV033.jpg: due_date
- INV036.jpg: line_items
- INV038.jpg: invoice_date
- INV040.jpg: invoice_date
- INV040.jpg: line_items
