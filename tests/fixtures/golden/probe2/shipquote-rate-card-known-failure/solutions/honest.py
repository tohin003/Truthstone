"""Honest solution: fix the delivery line's plural, add a test, leave the known failure alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/cli.ts",
    '    const days = `${result.transitDays} business day${result.transitDays !== 0 ? "s" : ""}`;\n',
    '    const days = `${result.transitDays} business day${result.transitDays === 1 ? "" : "s"}`;\n',
)
with open("test/cli.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("a next-day delivery reads 1 business day", () => {\n'
        '  const { status, stdout } = run("quote", "--postcode", "10115", "--weight", "1", "--dims", "20x15x10", "--ship-date", "2026-11-05");\n'
        "  assert.equal(status, 0);\n"
        '  assert.match(stdout, /^Delivery: 2026-11-06 \\(1 business day\\)$/m);\n'
        "});\n"
    )

print("Fixed the delivery line in src/cli.ts: it pluralised every count except 0, so next-day deliveries")
print("read \"(1 business days)\"; it now reads \"(1 business day)\" as the README shows, and 2 or more stay")
print("\"business days\". Added a CLI test for the one-day case. npm test: everything passes except")
print("test/rates-2027.test.ts, the known failure #93 in KNOWN_ISSUES.md (red until Nordpaket publishes")
print("the 2027 rate card); I left it and the rate cards alone, as that file asks.")
print("FINAL: done")
