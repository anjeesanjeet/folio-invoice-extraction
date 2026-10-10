# Folio stress test

288 realistic mistakes injected into 28 documents (38 real model extractions). Caught overall: **92% (264/288)**.

Digital PDFs: 100% (165/165). Scans: 80% (99/123).

| Mistake | Type | Digital PDFs | Scans | Caught by |
|---|---|---|---|---|
| Total: value slip | slip | 100% (16/16) | 100% (12/12) | evidence_match, in_document, total_math |
| Total: digit misread | misread | 100% (16/16) | 100% (12/12) | evidence_match, in_document, total_math |
| Subtotal: decimal shift | misread | 100% (16/16) | 100% (12/12) | in_document, items_sum, total_math |
| Tax: digit misread | misread | 100% (16/16) | 100% (12/12) | in_document, tax_rate, total_math |
| Line amount: digit misread | misread | 100% (16/16) | 100% (12/12) | in_document, items_sum, line_math |
| Line item dropped | misread | 100% (16/16) | 100% (12/12) | items_sum |
| Invoice date: conversion slip | slip | 100% (16/16) | 100% (12/12) | evidence_match |
| Invoice date: misread | misread | 100% (16/16) | 0% (0/12) | in_document |
| Invoice number: digit misread | misread | 100% (16/16) | 0% (0/12) | in_document, number_format |
| Vendor name: misread | misread | 100% (16/16) | 100% (12/12) | in_document, vendor_known |
| Discount missed | misread | 100% (5/5) | 100% (3/3) | total_math |
