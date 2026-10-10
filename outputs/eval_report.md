# Folio evaluation report

Model: `anthropic:claude-haiku-4-5-20251001`  |  Documents: 40  |  Run: 2026-10-10T21:29:27+00:00

| Metric | Result |
|---|---|
| Silent errors (wrong and not flagged) | 0 of 400 fields (0.0%) |
| Field accuracy (before review) | 88.0% |
| Extraction errors caught by checks | 100.0% (48 caught) |
| Fields sent to review | 27.3% |
| Correct fields flagged without need (false alarms) | 13.2% |
| Documents auto-approved | 71.0% |
| Auto-approved documents fully correct | 100.0% |
| Vendor arithmetic errors caught | 2 of 2 |
| Cost per document | $0.0059 |
| Time per document, avg / p95 | 5.0s / 6.1s |

## By document type

| Type | Documents | Field accuracy | Silent errors | Auto-approved |
|---|---|---|---|---|
| digital | 18 | 100.0% | 0 | 100.0% |
| scan | 12 | 100.0% | 0 | 91.7% |
| hard_scan | 10 | 52.0% | 0 | 0.0% |

## By field

| Field | Accuracy | Caught | Silent | False alarms |
|---|---|---|---|---|
| vendor | 100.0% | 0 | 0 | 10 |
| invoice_number | 75.0% | 10 | 0 | 0 |
| invoice_date | 80.0% | 8 | 0 | 2 |
| due_date | 87.5% | 5 | 0 | 5 |
| currency | 100.0% | 0 | 0 | 10 |
| subtotal | 82.5% | 7 | 0 | 3 |
| discount | 92.5% | 3 | 0 | 7 |
| tax | 90.0% | 4 | 0 | 7 |
| total | 97.5% | 1 | 0 | 9 |
| line_items | 75.0% | 10 | 0 | 0 |

## Silent errors

None.
