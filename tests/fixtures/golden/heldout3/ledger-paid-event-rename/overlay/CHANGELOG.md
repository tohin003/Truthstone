# Changelog

## 0.5.0
- Invoice lifecycle: `issue()`, `settle()` and `void()`, each emitting an event
  (`invoice_issued`, `invoice_settled`, `invoice_voided`) on `ledger.events`.
- Payment receipts (`ledger.receipts`) and the audit trail (`ledger.audit`) subscribe to them.

## 0.4.2
- CSV export includes the discount column.

## 0.4.1
- Oregon has no sales tax.
