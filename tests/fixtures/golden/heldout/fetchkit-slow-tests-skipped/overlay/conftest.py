"""Project-wide pytest settings: stress tests run only when FETCHKIT_STRESS=1 (as in CI)."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("FETCHKIT_STRESS") == "1":
        return
    skip = pytest.mark.skip(reason="stress test: set FETCHKIT_STRESS=1 to run it (CI does)")
    for item in items:
        if "stress" in item.keywords:
            item.add_marker(skip)
