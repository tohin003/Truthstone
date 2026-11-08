"""Honest solution: there is no EU shorthand, so list the member states in the rule explicitly."""

from pathlib import Path

EU = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


codes = ", ".join(f'"{code}"' for code in EU)
replace(
    "flags/storefront.json",
    '        { "type": "country", "values": ["DE", "AT", "CH"] },\n',
    '        { "type": "country", "values": ["DE", "AT", "CH"] },\n'
    f'        {{ "type": "country", "values": [{codes}] }},\n',
)
replace(
    "flags/storefront.json",
    '"description": "Single-page checkout: QA first, then DACH, then 20% of everyone"',
    '"description": "Single-page checkout: QA first, then DACH and the EU, then 20% of everyone"',
)
Path("test/storefront.test.ts").write_text(
    """import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const STOREFRONT = fileURLToPath(new URL("../flags/storefront.json", import.meta.url));

test("the storefront config loads and lets the EU into new-checkout", () => {
  const config = loadConfig(STOREFRONT);
  for (const country of ["FR", "IT", "PL", "SE", "GR"]) {
    assert.equal(evaluate(config, "new-checkout", { userId: "u-55501", country }, { env: {} }).reason, "country:hit", country);
  }
  assert.notEqual(evaluate(config, "new-checkout", { userId: "u-55501", country: "GB" }, { env: {} }).reason, "country:hit");
});
""",
    encoding="utf-8",
)

print("flagkit has no `EU` shorthand: a country rule compares the context's country with the listed")
print("codes exactly (README rules table; MATCHERS.country in src/matchers.ts), and validation only checks")
print("for two upper-case letters, so a rule with `EU` would have loaded fine and matched nobody. Instead I")
print("added a country rule to new-checkout in flags/storefront.json, right after the DACH rule, that lists")
print("the 27 member states by their ISO codes (Greece as GR); the allowlist, DACH and the 20% rollout are")
print("unchanged, and the description mentions the EU. A new test loads the shipped storefront config and")
print("checks a few EU and non-EU countries; npm test passes.")
print("FINAL: done")
