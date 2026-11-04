# `make check` is exactly what CI runs: the unit tests, then the integration suite.
PYTHON ?= python

.PHONY: check test integration

check: test integration

test:
	$(PYTHON) -m pytest -q tests

integration:
	$(PYTHON) -m pytest -q integration
