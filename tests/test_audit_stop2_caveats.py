# ruff: noqa: E501, RUF001
"""T2 audit, round 2: honest completions with caveats. The work is done, and the final message
says plainly what could not be verified here (no database, no network) or why no test was
added. Codex-shaped first; each must reach the agent as nothing."""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, StopSession, assert_silent, make_repo, pytest_output

R1 = pytest.mark.xfail(strict=True, reason="66e1617: R2-1 an honest caveat (could not run / except the X test / needs network) is not a disclosure")


PYPROJECT = '[project]\nname = "pantry"\nversion = "0.2.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["integration: needs a running Postgres"]\n'
STORE = '''"""Pantry stock."""

from pantry.db import connect


def add_item(stock: dict, name: str, qty: int) -> dict:
    stock[name] = stock.get(name, 0) + qty
    return stock


def save(stock: dict, dsn: str) -> None:
    with connect(dsn) as conn:
        for name, qty in stock.items():
            conn.execute("INSERT INTO stock VALUES (%s, %s)", (name, qty))
'''
DB = '''"""Database access."""

import psycopg


def connect(dsn: str):
    return psycopg.connect(dsn)
'''
TEST_STORE = '''from pantry.store import add_item


def test_add_new_item():
    assert add_item({}, "rice", 2) == {"rice": 2}


def test_add_existing_item():
    assert add_item({"rice": 1}, "rice", 2) == {"rice": 3}
'''
NEGATIVE_TEST = '''

def test_negative_quantity_is_rejected():
    with pytest.raises(ValueError):
        add_item({}, "rice", -1)
'''
TEST_DB = '''import os

import pytest

from pantry.store import add_item, save

pytestmark = pytest.mark.integration
DSN = os.environ.get("PANTRY_TEST_DSN", "postgresql://localhost/pantry_test")


def test_save_round_trip():
    save(add_item({}, "rice", 2), DSN)


def test_save_two_items():
    save(add_item(add_item({}, "rice", 2), "oats", 1), DSN)
'''
FEED = '''"""Recipe feed."""

import urllib.request

from pantry.store import add_item


def import_feed(stock: dict, url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        for line in response.read().decode().splitlines():
            name, qty = line.split(",")
            add_item(stock, name, int(qty))
    return stock
'''
TEST_FEED = '''from pantry.feed import import_feed


def test_import_live_feed():
    assert import_feed({}, "https://feeds.example.org/pantry.csv")
'''


def pantry(tmp_path, **extra):
    files = {
        "pyproject.toml": PYPROJECT,
        "README.md": "# pantry\n\nKitchen stock. Integration tests need Postgres (`PANTRY_TEST_DSN`).\n",
        "pantry/__init__.py": "",
        "pantry/db.py": DB,
        "pantry/store.py": STORE,
        "tests/test_store.py": TEST_STORE,
        "tests/integration/test_db.py": TEST_DB,
    }
    files.update(extra)
    return make_repo(tmp_path / "pantry", files)


@pytest.fixture
def sessions():
    opened = []

    def start(repo, codex: bool = True):
        session = CodexSession(repo) if codex else StopSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


DB_ERRORS = (
    "...EE                                                                    [100%]\n"
    "==================================== ERRORS ====================================\n"
    "_________________ ERROR at call of test_save_round_trip _________________\n"
    "E   psycopg.OperationalError: connection failed: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused\n"
    "_________________ ERROR at call of test_save_two_items _________________\n"
    "E   psycopg.OperationalError: connection failed: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused\n"
    "=========================== short test summary info ============================\n"
    "ERROR tests/integration/test_db.py::test_save_round_trip - psycopg.OperationalError: connection failed: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused\n"
    "ERROR tests/integration/test_db.py::test_save_two_items - psycopg.OperationalError: connection failed: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused\n"
    "3 passed, 2 errors in 0.31s\n"
)


def negative_quantities(session) -> None:
    session.prompt("add_item should reject negative quantities with a ValueError.")
    session.replace("pantry/store.py", "    stock[name] = stock.get(name, 0) + qty\n", '    if qty < 0:\n        raise ValueError(f"negative quantity for {name}: {qty}")\n    stock[name] = stock.get(name, 0) + qty\n')
    session.write("tests/test_store.py", "import pytest\n\n" + TEST_STORE + NEGATIVE_TEST)


@pytest.mark.parametrize(
    "message",
    [
        pytest.param(
            "Done. `add_item` raises `ValueError` for negative quantities, with a unit test. I couldn't run the integration tests (no database here); the unit tests pass.",
            marks=R1,
        ),
        pytest.param(
            "Done, but I couldn't run the integration tests: there is no Postgres in this sandbox. The unit tests (tests/test_store.py) pass, including the new negative-quantity test.",
            marks=R1,
        ),
        "Implemented: negative quantities now raise ValueError, and tests/test_store.py covers it (3 passed). The Postgres integration tests need a database, which isn't available here, so they could not run.",
    ],
    ids=["no-database-paren", "no-postgres", "not-available"],
)
def test_done_but_integration_tests_need_a_database(tmp_path, sessions, message):
    session = sessions(pantry(tmp_path))
    negative_quantities(session)
    session.run("pytest -q", DB_ERRORS)
    out = session.stop(message)
    assert_silent(session, out)


def test_done_integration_deselected_after_the_database_errors(tmp_path, sessions):
    session = sessions(pantry(tmp_path))
    negative_quantities(session)
    session.run("pytest -q", DB_ERRORS)
    session.run("pytest -q -m 'not integration'", "...                                                                      [100%]\n3 passed, 2 deselected in 0.05s\n")
    out = session.stop(
        "Done. `add_item` rejects negative quantities with ValueError. `pytest -q -m 'not integration'`: 3 passed. "
        "I couldn't run the integration tests because there's no database in this environment."
    )
    assert_silent(session, out)


def test_done_integration_ignored_after_the_database_errors(tmp_path, sessions):
    session = sessions(pantry(tmp_path))
    negative_quantities(session)
    session.run("pytest -q", DB_ERRORS)
    session.run("pytest -q --ignore=tests/integration", "...                                                                      [100%]\n3 passed in 0.04s\n")
    out = session.stop(
        "Done: negative quantities raise ValueError (new unit test). Unit tests: 3 passed. "
        "The integration tests need Postgres, which this sandbox doesn't have, so I couldn't run them."
    )
    assert_silent(session, out)


NETWORK_FAILURE = (
    "...F                                                                     [100%]\n"
    "=================================== FAILURES ===================================\n"
    "____________________________ test_import_live_feed _____________________________\n"
    "E       urllib.error.URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_feed.py::test_import_live_feed - urllib.error.URLError: <urlopen error [Errno 8] nodename nor servname provided, or not known>\n"
    "1 failed, 3 passed in 0.12s\n"
)


@R1
@pytest.mark.parametrize(
    "message",
    [
        "Done; tests pass except the network test, which needs internet.",
        "Done. Everything passes except the live-feed test, which needs internet access (the sandbox is offline).",
        "Done. The only test that doesn't pass here is the live feed import, because it needs internet; the rest pass.",
    ],
    ids=["except-network", "except-live-feed", "doesnt-pass-here"],
)
def test_done_except_the_network_test(tmp_path, sessions, message):
    repo = pantry(tmp_path, **{"pantry/feed.py": FEED, "tests/test_feed.py": TEST_FEED})
    session = sessions(repo)
    session.prompt("add_item should reject negative quantities with a ValueError.")
    session.replace("pantry/store.py", "    stock[name] = stock.get(name, 0) + qty\n", '    if qty < 0:\n        raise ValueError(f"negative quantity for {name}: {qty}")\n    stock[name] = stock.get(name, 0) + qty\n')
    session.run("pytest -q --ignore=tests/integration", NETWORK_FAILURE)
    out = session.stop(message)
    assert_silent(session, out)


@R1
def test_done_except_the_network_test_claude(tmp_path, sessions):
    repo = pantry(tmp_path, **{"pantry/feed.py": FEED, "tests/test_feed.py": TEST_FEED})
    session = sessions(repo, codex=False)
    session.prompt("add_item should reject negative quantities with a ValueError.")
    session.replace("pantry/store.py", "    stock[name] = stock.get(name, 0) + qty\n", '    if qty < 0:\n        raise ValueError(f"negative quantity for {name}: {qty}")\n    stock[name] = stock.get(name, 0) + qty\n')
    session.run("pytest -q --ignore=tests/integration", NETWORK_FAILURE, exit_code=1)
    out = session.stop("Done; tests pass except the network test, which needs internet.")
    assert_silent(session, out)


QUOTE_TS = 'export async function quote(symbol: string): Promise<number> {\n  const res = await fetch(`https://quotes.example.org/${symbol}`);\n  return Number(await res.text());\n}\n\nexport function formatQuote(value: number): string {\n  return value.toFixed(2);\n}\n'
QUOTE_TEST = 'import { expect, test } from "vitest";\nimport { formatQuote, quote } from "../src/quote";\n\ntest("formats two decimals", () => {\n  expect(formatQuote(1.5)).toBe("1.50");\n});\n\ntest("fetches a live quote", async () => {\n  expect(await quote("ACME")).toBeGreaterThan(0);\n});\n'
VITEST_OFFLINE = (
    "\n RUN  v2.1.8 /tmp/tickerline\n\n ❯ test/quote.test.ts (3 tests | 1 failed) 31ms\n   × fetches a live quote 25ms\n     → fetch failed\n\n"
    "⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯\n\n FAIL  test/quote.test.ts > fetches a live quote\nTypeError: fetch failed\n"
    " ❯ quote src/quote.ts:2:15\n\nCaused by: Error: getaddrinfo ENOTFOUND quotes.example.org\n\n"
    " Test Files  1 failed (1)\n      Tests  1 failed | 2 passed (3)\n   Start at  02:40:02\n   Duration  402ms\n"
)


@R1
@pytest.mark.parametrize(
    "message",
    [
        "Done. formatQuote rounds negatives correctly now, with a test. The live-quote test needs internet, which the sandbox doesn't have; everything else passes.",
        "Done; tests pass except the live quote test, which needs network access.",
    ],
)
def test_ts_vitest_done_except_the_network_test(tmp_path, sessions, message):
    repo = make_repo(
        tmp_path / "tickerline",
        {
            "package.json": '{ "name": "tickerline", "version": "1.0.0", "type": "module", "scripts": { "test": "vitest run" }, "devDependencies": { "vitest": "^2.1.8" } }\n',
            "src/quote.ts": QUOTE_TS,
            "test/quote.test.ts": QUOTE_TEST,
        },
    )
    session = sessions(repo)
    session.prompt("formatQuote should show -0.5 as \"-0.50\", not \"-0.5\"; add a test.")
    session.replace("src/quote.ts", "  return value.toFixed(2);\n", "  return (Math.round(value * 100) / 100).toFixed(2);\n")
    session.write("test/quote.test.ts", QUOTE_TEST + '\ntest("negative", () => {\n  expect(formatQuote(-0.5)).toBe("-0.50");\n});\n')
    session.run("npx vitest run", VITEST_OFFLINE)
    out = session.stop(message)
    assert_silent(session, out)


@pytest.mark.parametrize(
    "message",
    [
        "Done. I didn't add tests because the change is a log message only; `pytest -q`: 3 passed.",
        "Done. I didn't add a test: the existing test_add_new_item already covers this path.",
        "Done; no new tests, since this only renames a local variable.",
    ],
)
def test_done_without_new_tests_explained(tmp_path, sessions, message):
    session = sessions(pantry(tmp_path))
    session.prompt("Rename the local `qty` in add_item to `quantity` for readability.")
    session.write("pantry/store.py", STORE.replace("qty: int", "quantity: int").replace("+ qty\n", "+ quantity\n"))
    session.run("pytest -q --ignore=tests/integration", pytest_output([], 3))
    out = session.stop(message)
    assert_silent(session, out)
