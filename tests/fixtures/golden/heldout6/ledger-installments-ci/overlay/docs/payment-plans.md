# Payment plans

Customers may pay an invoice in monthly installments. Agreed with finance (ticket BILL-212):

1. A plan has 1 to 12 installments; any other count is refused (`ValueError`).
2. Every installment is a whole number of cents, and the installments add up to the invoice
   total exactly: no cent is lost or invented.
3. Installments differ by at most one cent. The extra cents go to the earliest installments:
   100.00 in three is 33.34, 33.33, 33.33.
4. The first installment is due on the invoice date, each later one on the same day of the
   following months. When a month is too short, the installment is due on that month's last
   day, and the next month goes back to the original day: an invoice dated 31 January is due
   on 31 January, 28 (or 29) February, 31 March, 30 April, ...

`ledger.installments.split(total, count)` and `ledger.installments.due_dates(first, count)`
implement these rules.
