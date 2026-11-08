# ledger

Small invoicing helpers used by the billing service.

```python
from decimal import Decimal
from ledger.invoice import Invoice, LineItem

invoice = Invoice("INV-1", "acme", "CA", [LineItem("W-1", "Widget", 3, Decimal("9.99"))])
print(invoice.total())
```

Amounts are `Decimal`. Rounding is commercial (half away from zero) to whole cents.
Discounts never exceed 50% of an invoice's subtotal.

## Payment references

Every invoice carries a structured creditor reference (ISO 11649, an "RF reference"), which the
customer's bank sends back with the transfer, so payments are matched to invoices automatically.
`ledger.references` makes and checks them; the tests in `tests/test_references.py` are the examples.

- `creditor_reference(invoice_number)`: `RF`, two check digits, then the invoice number with
  everything except letters and digits removed, in upper case. `INV-2026-0042` gives
  `RF73INV20260042`. That last part must be 1 to 21 characters long; anything else is a
  `ValueError`.
- The check digits: append `RF00` to that part, replace every letter by two digits (A = 10,
  B = 11, ..., Z = 35), take the resulting number modulo 97 and subtract the remainder from 98.
  They are always written with two digits (`RF05...`, never `RF5...`).
- `is_valid_reference(text)`: accepts a reference with or without spaces and in any case. It
  must be `RF`, two digits and 1 to 21 letters or digits, and its check digits must hold: move
  the first four characters to the end, replace the letters as above, and the number modulo 97
  must be 1. The standard's own example, `RF18 5390 0754 7034`, is valid.
- `format_reference(reference)`: the reference in groups of four, as printed on the invoice:
  `RF73 INV2 0260 042`.
- `Invoice.payment_reference()` is the invoice's reference.
