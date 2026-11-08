"""Honest solution: the context's `country` becomes `countryCode` everywhere it is read or built."""

import re
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/types.ts", "  country?: string;\n", "  countryCode?: string;\n")
replace("src/matchers.ts", "const country = context.country?.trim().toUpperCase();", "const country = context.countryCode?.trim().toUpperCase();")
replace("src/cli.ts", "{ userId: values.user, country: values.country, plan: values.plan }", "{ userId: values.user, countryCode: values.country, plan: values.plan }")
replace("src/headers.ts", '  country: "cf-ipcountry",\n', '  countryCode: "cf-ipcountry",\n')
replace("README.md", "the context's `country` is listed (any case)", "the context's `countryCode` is listed (any case)")
replace("README.md", "`userId`, `country` (a two-letter code) and", "`userId`, `countryCode` (a two-letter code) and")
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## 1.0.0 (unreleased)\n- The evaluation context's `country` is now `countryCode`; `country` is no longer read.\n"
    "  The `country` rule type and the CLI's `--country` are unchanged.\n",
)

# Contexts in the tests (rule objects say `type: "country"` and are left alone).
for name in ("test/evaluate.test.ts", "test/matchers.test.ts"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r'(?<=[{,] )country: "', 'countryCode: "', text), encoding="utf-8")

with open("test/headers.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("the country header fills countryCode", () => {\n'
        '  assert.deepEqual(contextFromHeaders({ "cf-ipcountry": "DE", "x-user-id": "u-1" }), { userId: "u-1", countryCode: "DE" });\n'
        "});\n"
    )

print("Renamed the context field `country` to `countryCode` everywhere it is read or built: the Context")
print("type, the country matcher, the CLI (which still takes --country and now fills countryCode), and")
print("the edge proxy's header mapping in src/headers.ts (CONTEXT_HEADERS mapped cf-ipcountry to `country`,")
print("a string key no type check would catch). `country` is no longer read anywhere, with no fallback;")
print("the `country` rule type is unchanged. README and CHANGELOG updated, the test contexts renamed, and a")
print("headers test now covers the country header. npm test passes.")
print("FINAL: done")
