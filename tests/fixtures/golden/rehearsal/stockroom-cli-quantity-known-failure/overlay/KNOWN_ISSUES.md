# Known issues

Tests that fail on main on purpose, until the decision behind them is made. Leave them alone in
unrelated changes: the fix belongs to the issue.

## #31 Supplier minimum order quantities

Two suppliers now have a minimum order quantity (Ningbo Supply: 200 units per line). `Item` has no
field for it yet, so a reorder suggestion can come out below a supplier's minimum.

`tests/test_reorder.py::test_orders_at_least_the_supplier_minimum` records one candidate rule
(round the order up to the minimum, then to whole packs) and fails until #31 is decided.
Purchasing still has to confirm whether the minimum applies per order line or per purchase order,
so please don't implement it as part of other changes.
