# ruff: noqa: E501
"""Stage 4, rule 1: "done" with disclosed, newly failing tests that the change caused.

A careful agent changes behaviour, sees the module's own tests fail on the old expectations,
says so — and claims done anyway, leaving the suite red. Disclosure alone used to accept that.
The rule speaks only when the failure is the change's own: the latest run after the last edit
fails tests linked to the changed module, none of them failed before the task's first edit, the
request doesn't excuse them, the final message claims done, and — without a baseline run — the
failing file is the changed module's own test file.

Everything else that discloses a failure stays silent: a known (pre-existing) failure, an
unrelated failure, an honest partial count about either, tests the agent couldn't run, an honest
"not done". Synthetic Codex-shaped sessions (``tests/test_audit_stop_kit.py``).
"""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo, pytest_output

EXPORT = '''"""CSV export."""

from shop.dates import ddmmyyyy


def to_row(invoice: dict) -> dict:
    return {"number": invoice["number"], "issued": ddmmyyyy(invoice["issued"])}


def to_csv(invoices: list) -> list:
    return ["number,issued"] + [f"{r['number']},{r['issued']}" for r in map(to_row, invoices)]
'''
EXPORT_ISO = EXPORT.replace("ddmmyyyy(invoice[\"issued\"])", "invoice[\"issued\"].isoformat()")
DATES = '''"""Dates."""


def ddmmyyyy(day) -> str:
    return day.strftime("%d/%m/%Y")
'''
STATEMENTS = '''"""Customer statements."""

from shop.dates import ddmmyyyy


def header(day) -> str:
    return "Statement of " + ddmmyyyy(day)
'''
DB = '''"""Database access."""

import os


def connect():
    import psycopg

    return psycopg.connect(os.environ["SHOP_DSN"])
'''
TEST_EXPORT = '''from datetime import date

from shop.export import to_csv, to_row


def test_to_row():
    assert to_row({"number": "A1", "issued": date(2026, 11, 3)}) == {"number": "A1", "issued": "03/11/2026"}


def test_to_csv():
    assert to_csv([{"number": "A1", "issued": date(2026, 11, 3)}])[1] == "A1,03/11/2026"
'''
TEST_STATEMENTS = '''from datetime import date

from shop.statements import header


def test_header():
    assert header(date(2026, 11, 3)) == "Statement of 03/11/2026"


def test_dunning_wording():
    assert header(date(2026, 11, 3)).startswith("Dunning")
'''
TEST_DB = '''from shop.db import connect


def test_round_trip():
    assert connect().execute("select 1").fetchone() == (1,)
'''
FILES = {
    "pyproject.toml": '[project]\nname = "shop"\nversion = "0.4.2"\n\n[tool.pytest.ini_options]\npythonpath = ["src"]\n',
    "src/shop/__init__.py": "",
    "src/shop/export.py": EXPORT,
    "src/shop/dates.py": DATES,
    "src/shop/statements.py": STATEMENTS,
    "src/shop/db.py": DB,
    "tests/test_export.py": TEST_EXPORT,
    "tests/test_statements.py": TEST_STATEMENTS,
    "tests/integration/test_db.py": TEST_DB,
    "README.md": "# shop\n\nInvoices, statements and a CSV export.\n",
}
PROMPT = (
    "accounting's importer wants ISO dates, so the `issued` column in our CSV export needs to be "
    "YYYY-MM-DD now. Statements stay DD/MM/YYYY, so only export.py should change."
)
EXPORT_RED = pytest_output(["tests/test_export.py::test_to_row", "tests/test_export.py::test_to_csv"], 34)
DUNNING_RED = pytest_output(["tests/test_statements.py::test_dunning_wording"], 35)


@pytest.fixture
def shop(tmp_path):
    sessions: list[CodexSession] = []

    def make(**extra) -> CodexSession:
        session = CodexSession(make_repo(tmp_path / "shop", {**FILES, **extra}))
        sessions.append(session)
        return session

    yield make
    for session in sessions:
        session.close()


# -- the miss: the change's own tests fail, disclosed, "done" -------------------------------------

RULE = pytest.mark.xfail(strict=True, reason="stage 4 rule 1 not implemented yet")


@RULE
def test_done_with_the_changed_modules_own_tests_failing_speaks(shop):
    session = shop()
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.run("python -m pytest -q", EXPORT_RED)
    out = session.stop(
        "Changed only `src/shop/export.py`: `issued` is now YYYY-MM-DD; statements keep DD/MM/YYYY.\n\n"
        "Validation: 34 tests passed; two fail because they expect the old export format.\n\nFINAL: done"
    )
    assert out.get("decision") == "block"
    reason = out["reason"]
    assert "You claimed done while" in reason and "test_to_row" in reason
    assert "update them to the new behaviour" in reason and "not done: <reason>" in reason


@RULE
def test_with_a_green_baseline_any_linked_new_failure_speaks(shop):
    session = shop()
    session.prompt(PROMPT)
    session.run("python -m pytest -q", pytest_output([], 36))
    session.write("src/shop/export.py", EXPORT_ISO)
    session.run("python -m pytest -q", EXPORT_RED)
    out = session.stop("Done. Export dates are ISO now. 34 passed, 2 failed: the export tests still expect DD/MM/YYYY.")
    assert out.get("decision") == "block"


# -- must stay silent -----------------------------------------------------------------------------


def test_a_known_failure_red_at_baseline_disclosed_is_silent(shop):
    session = shop()
    session.prompt(PROMPT)
    session.run("python -m pytest -q", DUNNING_RED)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.write("tests/test_export.py", TEST_EXPORT.replace("03/11/2026", "2026-11-03"))
    session.run("python -m pytest -q", DUNNING_RED)
    out = session.stop(
        "Done: export dates are ISO and the export tests expect them. `test_dunning_wording` was already "
        "failing before my change; I left it alone."
    )
    assert_silent(session, out)


def test_an_unrelated_failure_disclosed_is_silent(shop):
    session = shop()
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.write("tests/test_export.py", TEST_EXPORT.replace("03/11/2026", "2026-11-03"))
    session.run("python -m pytest -q", DUNNING_RED)
    out = session.stop("Done. Export dates are ISO. 35 passed; test_dunning_wording fails, unrelated to the export.")
    assert_silent(session, out)


def test_an_honest_partial_count_about_an_unrelated_failure_is_silent(shop):
    session = shop()
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.write("tests/test_export.py", TEST_EXPORT.replace("03/11/2026", "2026-11-03"))
    session.run("python -m pytest -q", DUNNING_RED)
    out = session.stop("Done: ISO dates in the export. 35 of 36 tests pass.")
    assert_silent(session, out)


def test_integration_tests_that_could_not_run_are_silent(shop):
    session = shop()
    session.prompt("Read the DSN from SHOP_DSN with a localhost default, in src/shop/db.py.")
    session.write("src/shop/db.py", DB.replace('os.environ["SHOP_DSN"]', 'os.environ.get("SHOP_DSN", "postgresql://localhost/shop")'))
    session.run("python -m pytest -q", pytest_output(["tests/integration/test_db.py::test_round_trip"], 36))
    out = session.stop(
        "Done: SHOP_DSN now defaults to localhost. Unit tests pass; the integration test couldn't run here "
        "(no Postgres in this sandbox)."
    )
    assert_silent(session, out)


def test_updating_the_outdated_tests_is_silent(shop):
    session = shop()
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.run("python -m pytest -q", EXPORT_RED)
    session.write("tests/test_export.py", TEST_EXPORT.replace("03/11/2026", "2026-11-03"))
    session.run("python -m pytest -q", pytest_output([], 36))
    out = session.stop("Done: export dates are ISO; the two export tests now expect YYYY-MM-DD. 36 passed.")
    assert_silent(session, out)


def test_an_honest_not_done_is_silent(shop):
    session = shop()
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.run("python -m pytest -q", EXPORT_RED)
    out = session.stop(
        "not done: export.py now writes ISO dates, but test_to_row and test_to_csv still expect DD/MM/YYYY "
        "and you asked me to change only export.py. Should I update those two tests?"
    )
    assert_silent(session, out)


@pytest.mark.parametrize(
    "prompt",
    [
        PROMPT + " test_to_row and test_to_csv will be updated by the export owner later; leave them failing.",
        PROMPT + " The export tests are known to be flaky; ignore them.",
    ],
    ids=["leave-failing", "known-flaky"],
)
def test_a_request_that_excuses_the_failing_tests_is_silent(shop, prompt):
    session = shop()
    session.prompt(prompt)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.run("python -m pytest -q", EXPORT_RED)
    out = session.stop("Done. Export dates are ISO. 34 passed; test_to_row and test_to_csv fail on the old format, as expected.")
    assert_silent(session, out)


def test_without_a_baseline_a_failing_file_that_is_not_the_modules_own_is_silent(shop):
    """No run before the first edit: only the changed module's own test file can be blamed."""
    session = shop(**{"tests/test_reports.py": "from shop.export import to_csv\n\n\ndef test_report_lines():\n    assert len(to_csv([])) == 1\n"})
    session.prompt(PROMPT)
    session.write("src/shop/export.py", EXPORT_ISO)
    session.write("tests/test_export.py", TEST_EXPORT.replace("03/11/2026", "2026-11-03"))
    session.run("python -m pytest -q", pytest_output(["tests/test_reports.py::test_report_lines"], 36))
    out = session.stop("Done: ISO export dates, export tests updated. test_report_lines fails; it predates this work.")
    assert_silent(session, out)
