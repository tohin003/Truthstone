"""Fixtures for the integration suite (`make integration`, or `make check` for everything)."""

import sqlite3
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def project_root() -> Path:
    """The checkout these tests belong to: the nearest directory with a pyproject.toml."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("cannot find the project root")


@pytest.fixture
def legacy_db(tmp_path) -> Path:
    """A copy of a reporting database created by datapipe 0.3.0, orders and import log included."""
    path = tmp_path / "reporting.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript((FIXTURES / "legacy-v1.sql").read_text(encoding="utf-8"))
    finally:
        conn.close()
    return path
