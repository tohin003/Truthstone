# Contributing to ledger

ledger has no runtime dependencies; please keep it that way.

## Tests

`python -m pytest` runs the whole suite, and CI runs it on every push. Nearly all of its time
(about a minute on a laptop) is `tests/test_fy2025_replay.py`, which re-totals every invoice of
the filed FY2025 year and compares the month figures with what accounting filed. While you
iterate, run the test file you are working on (`python -m pytest tests/test_discounts.py`);
before you push, run the whole suite, because the replay covers combinations of codes, regions
and amounts that no hand-written example does.

Issued totals never change (README, "Issued invoices"). Add a test with every change.
