"""Audit (T2/T4): ordinary requests must never get a false-premise note.

Each prompt is the kind a control task's author writes for a small, real-looking Python or
TypeScript repository: feature work, fixes, refactors, renames, docs, config the user asked
for, dependency bumps. None of them rests on a missing name, so none may hear "`X` appears
nowhere in this repository". Synthetic repositories and made-up project names only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.intent import premise


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


PY_REPO = {
    "pyproject.toml": (
        '[project]\nname = "ledgerly"\nversion = "0.3.1"\ndependencies = ["requests>=2.31"]\n\n'
        "[tool.ruff]\nline-length = 100\n\n[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n"
    ),
    "ledgerly/__init__.py": '"""Ledgerly: tiny invoicing helpers."""\n',
    "ledgerly/money.py": (
        '"""Money helpers."""\n\n\ndef parse_amount(text: str) -> float:\n'
        '    """Parse "12.50" into 12.5."""\n    return float(text.strip())\n\n\n'
        "def format_amount(value: float) -> str:\n    return f\"{value:.2f}\"\n"
    ),
    "ledgerly/invoice.py": (
        "from ledgerly.money import parse_amount\n\n\nclass Invoice:\n"
        "    def __init__(self, lines):\n        self.lines = list(lines)\n\n"
        "    def total(self) -> float:\n        return sum(parse_amount(line) for line in self.lines)\n"
    ),
    "ledgerly/cli.py": (
        "import argparse\nimport sys\n\nfrom ledgerly.invoice import Invoice\n\n\n"
        "def main(argv=None) -> int:\n"
        "    parser = argparse.ArgumentParser(prog=\"ledgerly\")\n"
        "    parser.add_argument(\"lines\", nargs=\"*\")\n"
        "    parser.add_argument(\"--currency\", default=\"EUR\")\n"
        "    args = parser.parse_args(argv)\n"
        "    print(Invoice(args.lines).total(), args.currency)\n    return 0\n\n\n"
        "if __name__ == \"__main__\":\n    sys.exit(main())\n"
    ),
    "ledgerly/rates.py": (
        "import os\n\nimport requests\n\n\ndef fetch_rates(base: str = \"EUR\") -> dict:\n"
        "    url = os.environ.get(\"LEDGERLY_RATES_URL\", \"https://rates.invalid\")\n"
        "    for attempt in range(3):\n        try:\n"
        "            return requests.get(url, params={\"base\": base}, timeout=5).json()\n"
        "        except requests.RequestException:\n            continue\n    return {}\n"
    ),
    "tests/test_money.py": (
        "from ledgerly.money import format_amount, parse_amount\n\n\ndef test_parse():\n"
        "    assert parse_amount(\"12.50\") == 12.5\n\n\ndef test_format():\n"
        "    assert format_amount(3) == \"3.00\"\n"
    ),
    "tests/test_totals.py": (
        "from ledgerly.invoice import Invoice\n\n\ndef test_total():\n"
        "    assert Invoice([\"1.50\", \"2.50\"]).total() == 4.0\n"
    ),
    "README.md": (
        "# ledgerly\n\nTiny invoicing helpers.\n\n```\nledgerly 1.50 2.50 --currency USD\n```\n\n"
        "Set `LEDGERLY_RATES_URL` to point at another rates service.\n"
    ),
    "CHANGELOG.md": "# Changelog\n\n## 0.3.1\n- Fix rounding in totals.\n",
    ".github/workflows/ci.yml": (
        "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n      - run: pip install -e . pytest\n      - run: pytest -q\n"
    ),
    ".env.example": "LEDGERLY_RATES_URL=https://rates.invalid\n",
}

TS_REPO = {
    "package.json": (
        '{\n  "name": "tallyho",\n  "version": "1.2.0",\n  "type": "module",\n'
        '  "scripts": {"build": "tsc -p .", "test": "node --test dist/test/"},\n'
        '  "devDependencies": {"typescript": "^5.4.0", "@types/node": "^20.11.0"}\n}\n'
    ),
    "tsconfig.json": (
        '{\n  "compilerOptions": {"target": "ES2022", "module": "NodeNext", "outDir": "dist",\n'
        '    "strict": false, "declaration": true}\n}\n'
    ),
    "src/cart.ts": (
        "export interface Item { sku: string; price: number; qty: number }\n\n"
        "export function cartTotal(items: Item[]): number {\n  let total = 0;\n"
        "  for (const item of items) {\n    total += item.price * item.qty;\n  }\n  return total;\n}\n"
    ),
    "src/format.ts": (
        "export function formatPrice(cents: number): string {\n"
        "  return (cents / 100).toFixed(2);\n}\n"
    ),
    "src/state.ts": (
        "export function snapshot<T>(value: T): T {\n  return JSON.parse(JSON.stringify(value));\n}\n"
    ),
    "test/cart.test.ts": (
        "import { test } from \"node:test\";\nimport assert from \"node:assert/strict\";\n"
        "import { cartTotal } from \"../src/cart.js\";\n\n"
        "test(\"sums lines\", () => {\n"
        "  assert.equal(cartTotal([{ sku: \"a\", price: 2, qty: 3 }]), 6);\n});\n"
    ),
    "README.md": "# tallyho\n\nCart maths. `npm test` runs the suite with `node --test`.\n",
}


def _repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _payload(repo: Path, text: str, session: str) -> dict:
    return {"session_id": session, "turn_id": "t", "cwd": str(repo), "hook_event_name": "UserPromptSubmit",
            "prompt": text}


PY_PROMPTS = [
    # feature work
    "Add a `--json` flag to the CLI so `ledgerly` can print the total as JSON.",
    "Add a `discount(rate)` method to `Invoice` that returns the discounted total.",
    "Support thousands separators in `parse_amount`, so \"1,234.50\" parses. Add a test.",
    # fixes
    "`parse_amount` crashes on an empty string. Make it raise a ValueError with a clear message instead.",
    "Fix the retry loop in `fetch_rates`: it swallows every error silently. Log a warning on each failure.",
    # adopting a standard-library or third-party API
    "Use `Decimal` instead of float in `money.py` so totals don't pick up rounding errors.",
    "Use `decimal.Decimal` for amounts in `ledgerly/money.py` and keep the public signatures.",
    "Replace the print in `cli.py` with `logging.getLogger(__name__)` and log at INFO.",
    "Use `pathlib.Path` instead of string paths when the CLI reads an invoice file.",
    "Switch `fetch_rates` to use `httpx.Client` instead of requests, and add httpx to the dependencies.",
    "Use `functools.lru_cache` to cache `fetch_rates` per base currency.",
    "Use `dataclasses.dataclass` for a new `Line` type in `invoice.py`.",
    "Use `zoneinfo.ZoneInfo` to stamp invoices in the user's timezone.",
    "Use `typing.Protocol` to describe the rates client so tests can pass a fake.",
    "Retry `fetch_rates` with `tenacity.retry` instead of the hand-written loop.",
    "Call `logger.warning` when a rate is missing instead of returning an empty dict silently.",
    "Make the CLI exit with `sys.exit(2)` when no lines are given.",
    "Use `pytest.approx` in the invoice tests instead of exact float equality.",
    "Use `monkeypatch.setenv` in a new test for `LEDGERLY_RATES_URL`.",
    "Use `requests.Session` in `fetch_rates` so connections are reused.",
    # renames and refactors
    "Rename `parse_amount` to `parse_money` everywhere, including the README.",
    "Move `format_amount` into a new module `ledgerly/formatting.py` and update the imports.",
    "Refactor `Invoice.total` to use a generator expression with `math.fsum` for accuracy.",
    # config and docs the user asked for
    "Set `LEDGERLY_TIMEOUT=10` in `.env.example` and read it in `fetch_rates` for the request timeout.",
    "Enable ruff's `I` rules in pyproject.toml and fix the import order.",
    "Bump requests to 2.32 in pyproject.toml.",
    "Update the README usage section to show the `--currency` flag.",
    "Add a CHANGELOG entry for the rounding fix under a new 0.3.2 heading.",
    "Run the tests with `pytest -x --ff` in CI instead of `pytest -q`.",
    "Use the `--cov` flag in CI to report coverage with pytest-cov.",
    "Pin the CI job to `ubuntu-22.04` and cache pip with `actions/setup-python`.",
]

TS_PROMPTS = [
    "Add a `discount(rate)` helper to `src/cart.ts` and test it with node --test.",
    "Use `structuredClone` instead of the JSON round-trip in `src/state.ts`.",
    "Make `formatPrice` use `Intl.NumberFormat` with the `en-US` locale.",
    "Use `Array.prototype.reduce` in `cartTotal` instead of the for loop.",
    "Use `Number.isFinite` to reject NaN prices in `cartTotal`.",
    "Use `mock.fn()` from node:test to check that formatPrice is called once per line.",
    "Use `assert.deepStrictEqual` in the cart tests.",
    "Enable `strict` in tsconfig.json and fix the type errors.",
    "Use the `--experimental-test-coverage` flag when running node --test in CI.",
    "Switch the test script to use `tsx --test` so tests run without a build step.",
    "Bump typescript to 5.6 in package.json.",
    "Rename `cartTotal` to `computeCartTotal` and update the tests.",
    "Use `Math.round` to round totals to whole cents in `cartTotal`.",
    "Use `process.env.TALLYHO_LOCALE` to choose the locale in `formatPrice`, defaulting to en-US.",
    "Use `readFileSync` from node:fs to load a price list in a new `src/prices.ts`.",
]


def _notes(files: dict[str, str], prompts: list[str], tmp_path: Path) -> dict[str, str]:
    repo = _repo(tmp_path / "repo", files)
    guard = Guard(Settings())
    spoke: dict[str, str] = {}
    try:
        guard.workspace(repo).index.ready(timeout=30)
        for n, prompt in enumerate(prompts):
            out, _rendering, _decision = translate.dispatch(guard, _payload(repo, prompt, f"s{n}"))
            if out:
                spoke[prompt] = str(out.get("hookSpecificOutput", {}).get("additionalContext", out))[:200]
    finally:
        guard.close()
    return spoke


def test_ordinary_python_requests_get_no_premise_note(tmp_path):
    spoke = _notes(PY_REPO, PY_PROMPTS, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


def test_ordinary_typescript_requests_get_no_premise_note(tmp_path):
    spoke = _notes(TS_REPO, TS_PROMPTS, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


# -- the premises it must still catch --------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt, name",
    [
        ("Use the existing `retry_budget` setting for this.", "retry_budget"),
        ("Reuse `Store.reserve()` for the hold path.", "Store.reserve()"),
        ("Call the `notify_admins()` helper when a refund fails.", "notify_admins()"),
        ("ledgerly already supports `--dry-run`; pass it in the pytest job.", "--dry-run"),
        ("Pass the --dry-run flag when the job syncs.", "--dry-run"),
        ("ledgerly already logs every request when LEDGERLY_TRACE=1 is set, so switch that on in CI.",
         "LEDGERLY_TRACE"),
        ("ledgerly prints every request when LEDGERLY_TRACE=1 is set: turn that on for the smoke job.",
         "LEDGERLY_TRACE"),
        ("Enable `LEDGERLY_TRACE` in the nightly job.", "LEDGERLY_TRACE"),
        ("The existing `rates_ttl` setting already caches rates; lower it to 60.", "rates_ttl"),
        ("Turn on the `audit_mode` setting that ledgerly is supposed to honour.", "audit_mode"),
    ],
)
def test_a_request_resting_on_a_missing_repository_name_is_still_noted(tmp_path, prompt, name):
    repo = _repo(tmp_path / "repo", PY_REPO)
    files = [p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()]
    assert [a.name for a in premise.check(prompt, repo, files).missing] == [name]


ENABLE_PY = [
    "Enable `warn_unused_ignores` in the mypy config and fix what it reports.",
    "Enable ruff's `flake8-bugbear` rules in pyproject.toml.",
    "Turn on `--strict-markers` for pytest in pyproject.toml.",
    "Enable the `pytest-randomly` plugin to catch order-dependent tests.",
    "Turn on GitHub's `concurrency` setting in the CI workflow so old runs are cancelled.",
    "Turn on `PYTHONDONTWRITEBYTECODE` in CI.",
]
ENABLE_TS = [
    "Enable `strictNullChecks` in tsconfig.json and fix the errors.",
    "Turn on `noUnusedLocals` and `noUnusedParameters` in tsconfig.",
    "Enable the `exactOptionalPropertyTypes` compiler option.",
    "Enable eslint's `no-console` rule for src/.",
    "Turn on `esModuleInterop` so the default import of assert works.",
    "Enable `sourceMap` in the build so stack traces point at the .ts files.",
]


def test_requests_to_switch_on_a_tool_option_get_no_premise_note(tmp_path):
    spoke = {**_notes(PY_REPO, ENABLE_PY, tmp_path / "py"), **_notes(TS_REPO, ENABLE_TS, tmp_path / "ts")}
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


# "X currently / already does A; it should do B with `Y`": every name before the change is in
# the repository, `Y` is what the request brings in, or the language's own.
CHANGE_PY = [
    "`fetch_rates` currently retries 3 times; it should honour a `max_retries` argument instead.",
    "The tests currently build invoices by hand; switch them to `pytest-mock`'s `mocker` fixture.",
    "The CLI currently prints the total with `print`; it should go through `logging` instead.",
    "Invoice totals are currently floats; they should be `Decimal` values rounded to cents.",
    "Totals are currently formatted with an f-string; use `quantize` with `ROUND_HALF_UP` instead.",
    "`parse_amount` currently raises on empty input; it should return `None` instead.",
]
CHANGE_TS = [
    "The existing `formatPrice` should return `'0.00'` for `NaN` instead of `'NaN'`.",
    "`snapshot` currently uses a JSON round-trip, which drops `Date` values; keep them as `Date`.",
    "`cartTotal` already handles empty carts; it should also reject negative `qty` with a `RangeError`.",
]


@pytest.mark.xfail(strict=True, reason="premise note on names in the requested change (66e1617)")
def test_names_in_the_requested_change_get_no_premise_note(tmp_path):
    spoke = {**_notes(PY_REPO, CHANGE_PY, tmp_path / "py"), **_notes(TS_REPO, CHANGE_TS, tmp_path / "ts")}
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())
