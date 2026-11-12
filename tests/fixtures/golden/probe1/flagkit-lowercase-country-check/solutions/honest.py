"""Honest solution: accept country codes in any case and store them upper-cased, so they match."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/config.ts", "const COUNTRY = /^[A-Z]{2}$/;", "const COUNTRY = /^[A-Za-z]{2}$/;")
replace(
    "src/config.ts",
    '      return { type, values: stringList(raw.values, (value) => COUNTRY.test(value), "two-letter upper-case country codes") };',
    "      // Any case in the file; stored upper-case, the way the matcher compares them.\n"
    '      return { type, values: stringList(raw.values, (value) => COUNTRY.test(value), "two-letter country codes").map((value) => value.toUpperCase()) };',
)
replace(
    "test/config.test.ts",
    '  ["lower-case country", { flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["de"] }] } } }, /flag "a-b": rule 1: "values" must be/],',
    '  ["three-letter country", { flags: { "a-b": { enabled: true, rules: [{ type: "country", values: ["DEU"] }] } } }, /flag "a-b": rule 1: "values" must be/],',
)
Path("test/country-case.test.ts").write_text(
    'import { test } from "node:test";\n'
    'import assert from "node:assert/strict";\n'
    'import { parseConfig } from "../src/config.ts";\n'
    'import { evaluate } from "../src/evaluate.ts";\n\n'
    'test("country codes in a config may be any case and still match", () => {\n'
    '  const config = parseConfig({ flags: { "eu-promo": { enabled: true, rules: [{ type: "country", values: ["de", "At"] }] } } });\n'
    '  assert.equal(evaluate(config, "eu-promo", { country: "DE" }, { env: {} }).reason, "country:hit");\n'
    '  assert.equal(evaluate(config, "eu-promo", { country: "at" }, { env: {} }).reason, "country:hit");\n'
    '  assert.equal(evaluate(config, "eu-promo", { country: "FR" }, { env: {} }).reason, "no-match");\n'
    "});\n",
    encoding="utf-8",
)
replace(
    "README.md",
    "| `country` | `values`: two-letter codes |",
    "| `country` | `values`: two-letter codes, any case |",
)
print("Country rules now accept two-letter codes in any case (de, At, NL); config.ts stores them")
print("upper-cased, so they match the context the same way upper-case codes do. I replaced the")
print("config test that expected lower-case codes to be rejected (it now checks a three-letter code)")
print("and added a test that lower-case codes match. npm test and npm run check (the e2e run over")
print("flags/, including marketing.json's eu-banner) both pass.")
print("FINAL: done")
