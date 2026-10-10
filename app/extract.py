"""The single model call: read the invoice images and return every field with the exact text it came from."""
from __future__ import annotations

from app.llm import BaseProvider

SCALAR_FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "discount", "tax", "total"]
ALL_FIELDS = SCALAR_FIELDS + ["line_items"]


def _field(kind: str, desc: str) -> dict:
    value = {"string": {"type": ["string", "null"]}, "number": {"type": ["number", "null"]},
             "date": {"type": ["string", "null"], "description": "ISO format YYYY-MM-DD"}}[kind]
    return {"type": "object", "description": desc, "properties": {
        "value": value,
        "evidence": {"type": ["string", "null"], "description": "The exact characters printed on the document for this value"},
    }, "required": ["value", "evidence"]}


SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": _field("string", "Company that issued the invoice (the seller), not the customer"),
        "invoice_number": _field("string", "Invoice / bill number exactly as printed"),
        "invoice_date": _field("date", "Issue date"),
        "due_date": _field("date", "Payment due date; null if not printed"),
        "currency": _field("string", "ISO 4217 code, e.g. USD, INR, EUR, GBP"),
        "subtotal": _field("number", "Sum of line items before discount and tax"),
        "discount": _field("number", "Discount as a positive number; null if none"),
        "tax": _field("number", "Total tax amount (GST, VAT, sales tax)"),
        "total": _field("number", "Final amount payable as printed, even if it looks wrong"),
        "line_items": {"type": "array", "items": {"type": "object", "properties": {
            "description": {"type": "string"}, "quantity": {"type": ["number", "null"]},
            "unit_price": {"type": ["number", "null"]}, "amount": {"type": ["number", "null"]}},
            "required": ["description", "quantity", "unit_price", "amount"]}},
        "uncertain_fields": {"type": "array", "items": {"type": "string"},
                             "description": "Names of fields that are hard to read or ambiguous on the document"},
    },
    "required": ALL_FIELDS + ["uncertain_fields"],
}

SYSTEM = """You extract data from invoices for an accounts-payable team. Accuracy matters more than completeness.
Rules:
- Copy what is printed. Never calculate, correct or fill in a value that is not on the document.
- If the printed total does not match the items, still return the printed total.
- Numbers: plain numbers with a dot for decimals (1.234,50 -> 1234.5; 1,23,456.00 -> 123456). Discount as a positive number.
- Dates: convert to YYYY-MM-DD using the vendor's country conventions (e.g. 26.08.2026 is 26 August).
- evidence: the exact characters printed for that value, e.g. "Rs. 12,816.48" or "26-08-2026".
- Use null when a field is not printed. List hard-to-read or ambiguous fields in uncertain_fields."""


def extract(provider: BaseProvider, pages: list[bytes], text_layer: str = ""):
    prompt = "Extract the invoice fields from the page image(s)."
    if text_layer:
        prompt += "\n\nThe PDF also has this text layer (use it to read characters precisely):\n" + text_layer[:6000]
    return provider.extract(SYSTEM, prompt, pages, "submit_invoice", SCHEMA, max_tokens=3000)
