# `make check` is exactly what CI runs: the unit tests, then the replay of recorded gateway traffic.
PYTHON ?= python

.PHONY: check test replay

check: test replay

test:
	$(PYTHON) -m pytest -q

replay:
	$(PYTHON) scripts/replay.py
