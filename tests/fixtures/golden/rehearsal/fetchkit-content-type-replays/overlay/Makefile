# `make check` is what CI runs: the unit tests, then the recorded-traffic replays.
PYTHON ?= python

.PHONY: check test replay

check: test replay

test:
	$(PYTHON) -m pytest -q tests

replay:
	$(PYTHON) -m pytest -q replay
