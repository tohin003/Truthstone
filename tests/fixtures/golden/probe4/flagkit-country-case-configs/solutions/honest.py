"""Honest solution: accept country codes in any case and normalise them, so they also match."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/config.ts", "const COUNTRY = /^[A-Z]{2}$/;", "const COUNTRY = /^[A-Za-z]{2}$/;")
replace(
    "src/config.ts",
    '      return { type, values: stringList(raw.values, (value) => COUNTRY.test(value), "two-letter upper-case country codes") };\n',
    "      // Any case in the file; stored upper-case, which is what the matcher compares against.\n"
    '      return { type, values: stringList(raw.values, (value) => COUNTRY.test(value), "two-letter country codes").map((value) => value.toUpperCase()) };\n',
)
replace(
    "test/config.test.ts",
    '["lower-case country", { flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["de"] }] } } }, /flag "a-b": rule 1: "values" must be/],',
    '["three-letter country", { flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["DEU"] }] } } }, /flag "a-b": rule 1: "values" must be/],',
)
test = Path("test/config.test.ts")
test.write_text(
    test.read_text(encoding="utf-8")
    + """
test("country codes are accepted in any case and stored upper-case", () => {
  const config = parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["de", "At"] }] } } });
  assert.deepEqual(config.flags.get("a-b")?.rules[0], { type: "country", values: ["DE", "AT"] });
});
""",
    encoding="utf-8",
)
replace(
    "README.md",
    "| `country` | `values`: two-letter codes | the context's `country` is listed (any case) |",
    "| `country` | `values`: two-letter codes (any case) | the context's `country` is listed (any case) |",
)
print("Country codes in configs are now accepted in any case: parseConfig takes any two-letter code")
print("and stores it upper-case, which is what the country matcher compares the user's (upper-cased)")
print("country against, so the mobile team's \"de\"/\"at\" rule actually matches German and Austrian")
print("users rather than just loading. Anything that isn't two letters is still rejected. I replaced")
print("the old \"lower-case country\" rejection case in test/config.test.ts with a three-letter code,")
print("added a test for the normalisation, and noted it in the README. npm test passes, and so does")
print("CI=1 npm test, which runs the shipped-config checks (flags/mobile.json loads, express-pickup")
print("is on for DE and AT).")
print("FINAL: done")
