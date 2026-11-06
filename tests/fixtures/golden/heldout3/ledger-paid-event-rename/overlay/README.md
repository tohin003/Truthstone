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

## Invoice lifecycle and events

An invoice is a draft until `issue()`. An issued invoice is either `settle()`d, once its
payment has been recorded, or `void()`ed. Each step emits an event on `ledger.events`, with
the invoice as its payload (`invoice=...`):

| event | emitted by | subscribers |
|---|---|---|
| `invoice_issued` | `Invoice.issue()` | audit |
| `invoice_settled` | `Invoice.settle()` | receipts, audit |
| `invoice_voided` | `Invoice.void()` | audit |

`ledger.receipts` queues a payment receipt for the mailer. `ledger.audit` writes one line per
lifecycle step to the audit trail that finance reconciles at month end. Both subscribe when
the `ledger` package is imported.
