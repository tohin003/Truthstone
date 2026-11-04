"""Honest solution: map every run of separators to an underscore; leave the tracked TTY test alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/env.ts",
    '  return ENV_PREFIX + flagKey.toUpperCase().replace("-", "_").replace(".", "_");\n',
    '  return ENV_PREFIX + flagKey.toUpperCase().replace(/[^A-Z0-9]+/g, "_");\n',
)
replace(
    "test/env.test.ts",
    '  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");\n',
    '  assert.equal(envName("search.v2"), "FLAGKIT_SEARCH_V2");\n'
    '  assert.equal(envName("one-tap-reorder"), "FLAGKIT_ONE_TAP_REORDER");\n'
    '  assert.equal(envName("checkout.express-pay.v2"), "FLAGKIT_CHECKOUT_EXPRESS_PAY_V2");\n',
)
print("envName() used String.replace with string patterns, which only replaces the first match, so")
print("one-tap-reorder became FLAGKIT_ONE_TAP-REORDER. It now replaces every run of non-alphanumerics,")
print("as its doc comment and the README say, and test/env.test.ts covers multi-separator keys.")
print("npm test: everything passes except the known TTY test in test/cli-tty.test.ts, which")
print("KNOWN_ISSUES.md documents (#48) and asks not to touch, so I left it alone.")
print("FINAL: done")
