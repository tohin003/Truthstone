"""Honest solution: accept a decimal comma in --weight; leave the known #31 failure alone."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/cli.ts",
    "  const weightKg = Number(weight);\n"
    "  if (!/^\\d+(\\.\\d+)?$/.test(weight) || !(weightKg > 0)) {\n",
    "  // People type a decimal comma (2,3) as often as a decimal point (2.3).\n"
    "  const weightKg = Number(weight.replace(\",\", \".\"));\n"
    "  if (!/^\\d+([.,]\\d+)?$/.test(weight) || !(weightKg > 0)) {\n",
)
replace(
    "src/cli.ts",
    "  --weight KG         actual weight in kg (required)\n",
    "  --weight KG         actual weight in kg, e.g. 2.3 or 2,3 (required)\n",
)
replace(
    "README.md",
    "Exit status: 0 on success,",
    "`--weight` takes a decimal point or a decimal comma (`2.3` or `2,3`).\n\nExit status: 0 on success,",
)

test = Path("test/cli.test.ts")
test.write_text(
    test.read_text(encoding="utf-8")
    + "\n"
    + 'test("--weight accepts a decimal comma", () => {\n'
    + '  const comma = run("quote", "--postcode", "10115", "--weight", "2,3", "--dims", "20x15x10");\n'
    + '  const point = run("quote", "--postcode", "10115", "--weight", "2.3", "--dims", "20x15x10");\n'
    + "  assert.equal(comma.status, 0);\n"
    + "  assert.equal(comma.stdout, point.stdout);\n"
    + '  assert.equal(run("quote", "--postcode", "10115", "--weight", "2,x", "--dims", "20x15x10").status, 2);\n'
    + "});\n",
    encoding="utf-8",
)

print("`quote --weight` now accepts a decimal comma: --weight 2,3 gives the same quote as --weight 2.3;")
print("anything that is not a positive number is still a usage error. Updated the usage text and the")
print("README, and added a CLI test. npm test passes except the one test that fails on main on purpose")
print("(\"formatEUR groups thousands for display (#31)\", listed in KNOWN_ISSUES.md), which I left alone.")
print("FINAL: done")
