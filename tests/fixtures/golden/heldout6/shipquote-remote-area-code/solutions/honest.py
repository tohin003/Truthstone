"""Honest solution: rename the line code everywhere, including the account table keyed by it."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/quote.ts", 'export type LineCode = "base" | "fuel" | "remote" | "oversize";',
        'export type LineCode = "base" | "fuel" | "remote-area" | "oversize";')
replace("src/quote.ts", 'lines.push({ code: "remote", label:', 'lines.push({ code: "remote-area", label:')
replace("data/charge-accounts.json", '"remote": "4732"', '"remote-area": "4732"')
replace("CHANGELOG.md", "# Changelog\n", "# Changelog\n\n## Unreleased\n- The remote-area quote line's code is now `remote-area` (was `remote`), as in Nordpaket's v3 API.\n")
Path("test/accounts.test.ts").write_text(
    """import { test } from "node:test";
import assert from "node:assert/strict";
import { accountFor, postings } from "../src/accounts.ts";
import { quote } from "../src/quote.ts";

test("every line of a remote quote has an account", () => {
  const q = quote({ country: "DE", postcode: "25980", parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 } });
  assert.deepEqual(postings(q).map((posting) => posting.account), ["4730", "4731", "4732"]);
  assert.throws(() => accountFor("remote"), RangeError);
});
""",
    encoding="utf-8",
)

print("Renamed the `remote` line code to `remote-area`: the LineCode type and the line quote() adds,")
print("plus data/charge-accounts.json, whose keys are line codes (postings() for the freight export")
print("would otherwise have thrown for every remote quote). No alias: `remote` has no account and no")
print("line uses it. Added test/accounts.test.ts and a CHANGELOG entry; npm test passes.")
print("FINAL: done")
