# Changelog

## 0.5.2
- `monthly_revenue` works out the month's first and last day once, instead of per invoice.

## 0.5.1
- The report tests build their invoices from plain dates, so they no longer depend on the
  machine's time zone (#44).

## 0.5.0
- Invoices carry `issued_on` (None while a draft).
- `reports.monthly_revenue(invoices, year, month)`: revenue per region for one calendar month,
  for finance's month-end close.

## 0.4.2
- CSV export includes the discount column.

## 0.4.1
- Oregon has no sales tax.
