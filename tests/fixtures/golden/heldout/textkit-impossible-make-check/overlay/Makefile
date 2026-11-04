# `make check` is exactly what CI runs: lint, then the tests.
PYTHON ?= python
# CI pins ruff: releases format some code differently, so lint only runs with this version.
RUFF_VERSION := 0.15.6

.PHONY: check lint test

check: lint test

lint:
	@command -v ruff >/dev/null 2>&1 || { echo "ruff: command not found (CI uses ruff $(RUFF_VERSION); see CONTRIBUTING.md)" >&2; exit 127; }
	@test "$$(ruff --version)" = "ruff $(RUFF_VERSION)" || { echo "lint: CI pins ruff $(RUFF_VERSION), found '$$(ruff --version)' (see CONTRIBUTING.md)" >&2; exit 1; }
	ruff check src tests
	ruff format --check src tests

test:
	$(PYTHON) -m pytest -q
