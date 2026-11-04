# Contributing to stockroom

stockroom has no runtime dependencies; please keep it that way.

## Tests

`python -m pytest` runs the whole suite, which CI runs on every push. Nearly all of its time
(a minute or two on a laptop) is `tests/test_reorder_simulation.py`, which replays three years
of demand for an 18,000-item catalogue against the reorder policy. While you iterate, run the
test file you are working on (`python -m pytest tests/test_reorder.py`); before you push, run
the whole suite, because the modules share the inventory and a change in one shows up in the
tests of another.

Add a test with every fix.
