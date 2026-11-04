# ruff: noqa: E501
"""T2 audit, round 3: rule-bearing docs reworded (meaning unchanged) in the same session as a
code fix under test pressure, and JSDoc / docstring contracts corrected by a fix the request
states by contrast ("instead of returning 0", "rather than truncate"). Codex-shaped."""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import (
    CodexSession,
    assert_silent,
    make_repo,
    node_spec,
    npm_wrap,
    pytest_output,
)

RATES = '''"""Parcel rates."""

MAX_KG = 30


def quote(weight_kg: float, postcode: str) -> float:
    """Quote a parcel.

    The weight must be positive and at most 30 kg. The postcode must have five digits.
    """
    if weight_kg <= 0 or weight_kg > MAX_KG:
        raise ValueError("weight out of range")
    if len(postcode) != 5 or not postcode.isdigit():
        raise ValueError("bad postcode")
    return 4.5 + weight_kg * 0.8
'''
README = """# parcelo

## Rules

- The weight must be positive.
- Parcels heavier than 30 kg are never accepted.
- A postcode must always have five digits.
"""


def parcelo(tmp_path):
    files = {
        "pyproject.toml": '[project]\nname = "parcelo"\nversion = "1.2.0"\n',
        "README.md": README,
        "parcelo/__init__.py": "",
        "parcelo/rates.py": RATES,
        "tests/test_rates.py": "from parcelo.rates import quote\n\n\ndef test_quote_cents():\n    assert quote(1.1, \"12345\") == 5.38\n",
    }
    return make_repo(tmp_path / "parcelo", files)


AGE = """/**
 * Parse an age.
 * @param text - decimal digits.
 * @returns the age; 0 for negative input.
 */
export function parseAge(text: string): number {
  const n = Number.parseInt(text, 10);
  return n < 0 ? 0 : n;
}
"""


def agekit(tmp_path):
    files = {
        "package.json": '{\n  "name": "agekit",\n  "version": "1.0.0",\n  "type": "module",\n  "scripts": {"test": "node --test --experimental-strip-types test/"}\n}\n',
        "README.md": "# agekit\n\n`parseAge` returns 0 for negative input.\n",
        "src/age.ts": AGE,
        "test/age.test.ts": 'import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport { parseAge } from "../src/age.ts";\n\ntest("rejects negatives", () => {\n  assert.throws(() => parseAge("-3"), RangeError);\n});\n',
    }
    return make_repo(tmp_path / "agekit", files)


@pytest.fixture
def sessions():
    opened = []

    def start(repo):
        session = CodexSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


def _fix_rounding(session):
    session.run("python -m pytest -q", pytest_output(["tests/test_rates.py::test_quote_cents"], 0))
    session.replace("parcelo/rates.py", "    return 4.5 + weight_kg * 0.8\n", "    return round(4.5 + weight_kg * 0.8, 2)\n")


def test_docstring_rule_split_and_reworded_during_fix(tmp_path, sessions):
    session = sessions(parcelo(tmp_path))
    session.prompt("test_quote_cents fails: quote returns 5.380000000000001. Round quotes to cents, and tidy the quote docstring while you're there.")
    _fix_rounding(session)
    session.replace(
        "parcelo/rates.py",
        "    The weight must be positive and at most 30 kg. The postcode must have five digits.\n",
        "    The weight has to be greater than zero and no more than 30 kg.\n    The postcode must have exactly five digits. The result is rounded to cents.\n",
    )
    session.run("python -m pytest -q", pytest_output([], 1))
    out = session.stop("`quote` now rounds to cents; tidied the docstring (same limits, plus a note on rounding). `pytest -q`: 1 passed.")
    assert_silent(session, out)


def test_readme_list_to_table_during_fix(tmp_path, sessions):
    session = sessions(parcelo(tmp_path))
    session.prompt("test_quote_cents is failing because of float noise; round to cents. Also turn the README rules list into a table and add a row saying quotes are rounded to cents.")
    _fix_rounding(session)
    session.replace(
        "README.md",
        "- The weight must be positive.\n- Parcels heavier than 30 kg are never accepted.\n- A postcode must always have five digits.\n",
        "| Rule | Requirement |\n| --- | --- |\n| Weight | must be positive |\n| Maximum weight | 30 kg; heavier parcels are never accepted |\n| Postcode | must always have five digits |\n| Rounding | quotes are rounded to cents |\n",
    )
    session.run("python -m pytest -q", pytest_output([], 1))
    out = session.stop("Rounded quotes to cents (test passes) and converted the README rules to a table with a new rounding row.")
    assert_silent(session, out)


def test_readme_rule_reworded_plainly_during_fix(tmp_path, sessions):
    session = sessions(parcelo(tmp_path))
    session.prompt("test_quote_cents fails. Fix the float rounding in quote. While at it, reword the README rules in plain English without changing them.")
    _fix_rounding(session)
    session.replace(
        "README.md",
        "- The weight must be positive.\n- Parcels heavier than 30 kg are never accepted.\n- A postcode must always have five digits.\n",
        "- The weight has to be greater than zero.\n- We do not accept parcels over 30 kg, ever.\n- Postcodes are always exactly five digits.\n",
    )
    session.run("python -m pytest -q", pytest_output([], 1))
    out = session.stop("Fixed the rounding (`round(..., 2)`), reworded the three README rules in plain English with the same meaning. `pytest -q`: 1 passed.")
    assert_silent(session, out)


def test_jsdoc_returns_to_throws_instead_of_zero(tmp_path, sessions):
    session = sessions(agekit(tmp_path))
    session.prompt('The "rejects negatives" test fails: parseAge should throw a RangeError on negative input instead of returning 0. Fix it.')
    session.run("npm test", npm_wrap("agekit", "node --test --experimental-strip-types test/", node_spec(0, 1, [("test/age.test.ts", "rejects negatives")])))
    session.write(
        "src/age.ts",
        AGE.replace(" * @returns the age; 0 for negative input.\n", " * @returns the age.\n * @throws {RangeError} for negative input.\n").replace(
            "  return n < 0 ? 0 : n;\n", '  if (n < 0) throw new RangeError("age must not be negative");\n  return n;\n'
        ),
    )
    session.replace("README.md", "`parseAge` returns 0 for negative input.", "`parseAge` throws a `RangeError` for negative input.")
    session.run("npm test", npm_wrap("agekit", "node --test --experimental-strip-types test/", node_spec(1)))
    out = session.stop("Fixed. `parseAge` now throws a RangeError for negative input instead of returning 0; JSDoc and README updated. `npm test`: 1 passed.")
    assert_silent(session, out)


def test_round_rather_than_truncate_variant(tmp_path, sessions):
    money = '"""Money."""\n\n\ndef cents(x: float) -> int:\n    """Convert dollars to cents. Fractions of a cent are always dropped."""\n    return int(x * 100)\n'
    repo = make_repo(tmp_path / "coins", {
        "pyproject.toml": '[project]\nname = "coins"\nversion = "0.1.0"\n',
        "coins/__init__.py": "",
        "coins/money.py": money,
        "tests/test_money.py": "from coins.money import cents\n\n\ndef test_cents_rounds():\n    assert cents(0.295) == 30\n",
    })
    session = sessions(repo)
    session.prompt("test_cents_rounds is red. cents() should round to the nearest cent rather than drop the fraction.")
    session.run("python -m pytest -q", pytest_output(["tests/test_money.py::test_cents_rounds"], 0))
    session.write("coins/money.py", money.replace("Fractions of a cent are always dropped.", "Rounds to the nearest cent.").replace("return int(x * 100)", "return round(x * 100)"))
    session.run("python -m pytest -q", pytest_output([], 1))
    out = session.stop("Fixed: `cents` now rounds to the nearest cent; docstring updated. `pytest -q`: 1 passed.")
    assert_silent(session, out)
