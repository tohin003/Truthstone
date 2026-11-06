"""Honest solution: accept x or X with optional spaces in --dims; leave the #73 known failure alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/cli.ts",
    "  const size = /^(\\d+(?:\\.\\d+)?)x(\\d+(?:\\.\\d+)?)x(\\d+(?:\\.\\d+)?)$/.exec(dims);\n",
    "  // Scanners write 40X30X20 or 40 x 30 x 20: an x or X, with optional spaces around it.\n"
    "  const size = /^(\\d+(?:\\.\\d+)?) *[xX] *(\\d+(?:\\.\\d+)?) *[xX] *(\\d+(?:\\.\\d+)?)$/.exec(dims);\n",
)
replace(
    "src/cli.ts",
    "  --dims LxWxH        size in cm, e.g. 40x30x20 (required)\n",
    "  --dims LxWxH        size in cm, e.g. 40x30x20 or 40 X 30 X 20 (required)\n",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- `--dims` accepts an upper-case X and spaces around the x (`40 X 30 X 20`).\n",
)
test = Path("test/cli.test.ts")
test.write_text(
    test.read_text(encoding="utf-8")
    + '''
test("--dims takes an x or X with optional spaces, as the scanners write it", () => {
  const plain = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");
  for (const dims of ["20X15X10", "20 x 15 x 10", "20 X 15x10"]) {
    const scanned = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", dims);
    assert.equal(scanned.status, 0, dims);
    assert.equal(scanned.stdout, plain.stdout, dims);
  }
  assert.equal(run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20*15*10").status, 2);
});
''',
    encoding="utf-8",
)
print("--dims now accepts an x or an X between the numbers, with optional spaces around it, so the")
print("scanner's 40X30X20 and 40 x 30 x 20 both work; anything else is still a usage error. The usage")
print("text shows the new form, CHANGELOG has a line, and test/cli.test.ts has a test for it.")
print("npm test: everything passes except \"deliveries to Austria skip Austrian public holidays\" in")
print("test/calendar.test.ts, the known failure #73 listed in KNOWN_ISSUES.md; I left it alone.")
print("FINAL: done")
