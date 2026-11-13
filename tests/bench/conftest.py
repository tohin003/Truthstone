"""Shared fixtures for the benchmark harness tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_codex_binary_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """`plan` records the Codex CLI's version (`cli.codex_version` runs `codex --version`). No test
    may need a Codex binary on the machine: a CI runner has none (FileNotFoundError), and a
    developer's would make the plan depend on whatever they have installed."""
    from truthstone.bench.codex import cli

    monkeypatch.setattr(cli, "codex_version", lambda codex_bin: "0.0.0-test")
