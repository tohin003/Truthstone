.PHONY: test check

# Unit tests only (what plain `pytest` runs).
test:
	python -m pytest -q tests

# What CI runs: the unit tests and the recorded edge proxy sessions.
check:
	python -m pytest -q tests integration
