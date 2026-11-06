# Contributing to textkit

## Running the tests

    pytest

The test suite is everything under `tests/`, and nothing else. CI runs `pytest` from the
repository root of a fresh clone, on Python 3.11 to 3.13. textkit has no runtime
dependencies, so there is nothing to install first.

## Experiments

Try ideas out in `experiments/` before they go into the package: sketches, sample data,
notes. That folder belongs to whoever works in the checkout; it is not committed and nothing
in it ships. Once an idea is ready, move the code into `src/textkit/` and its tests into
`tests/`.

## Changes

Every change gets a line in CHANGELOG.md under "Unreleased".
