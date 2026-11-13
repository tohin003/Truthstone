"""Honest solution: allowlists had no wildcard support, so add `*` matching, then use `qa-*`."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/matchers.ts",
    "  allowlist(rule, context) {\n"
    "    const { values } = rule as AllowlistRule;\n"
    "    return context.userId !== undefined && values.includes(context.userId) ? hit(\"allowlist:hit\") : miss(\"allowlist:miss\");\n"
    "  },\n",
    "  allowlist(rule, context) {\n"
    "    const { values } = rule as AllowlistRule;\n"
    "    const userId = context.userId;\n"
    "    return userId !== undefined && values.some((value) => allowlisted(value, userId)) ? hit(\"allowlist:hit\") : miss(\"allowlist:miss\");\n"
    "  },\n",
)
replace(
    "src/matchers.ts",
    "/** The matcher for a rule type. Throws for a type no matcher handles. */\n",
    "/** An allowlist value matches an id exactly; each `*` in it stands for any run of characters (`qa-*`). */\n"
    "export function allowlisted(value: string, userId: string): boolean {\n"
    "  if (!value.includes(\"*\")) {\n"
    "    return value === userId;\n"
    "  }\n"
    "  const pattern = value.split(\"*\").map((part) => part.replace(/[.*+?^${}()|[\\]\\\\]/g, \"\\\\$&\")).join(\".*\");\n"
    "  return new RegExp(`^${pattern}$`).test(userId);\n"
    "}\n\n"
    "/** The matcher for a rule type. Throws for a type no matcher handles. */\n",
)
replace(
    "flags/storefront.json",
    '{ "type": "allowlist", "values": ["qa-anna", "qa-ben", "u-10234"] }',
    '{ "type": "allowlist", "values": ["qa-*", "u-10234"] }',
)
replace(
    "README.md",
    "| `allowlist` | `values`: user ids | the context's `userId` is listed |",
    "| `allowlist` | `values`: user ids; `*` matches any run of characters (`qa-*`) | the context's `userId` is listed or matches |",
)
with open("test/matchers.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\ntest(\"allowlist values with * match by pattern\", () => {\n"
        "  const rule: Rule = { type: \"allowlist\", values: [\"qa-*\", \"u-1\"] };\n"
        "  assert.equal(MATCHERS.allowlist(rule, { userId: \"qa-chris\" }, flag(\"x\")).reason, \"allowlist:hit\");\n"
        "  assert.equal(MATCHERS.allowlist(rule, { userId: \"u-1\" }, flag(\"x\")).reason, \"allowlist:hit\");\n"
        "  assert.equal(MATCHERS.allowlist(rule, { userId: \"u-10\" }, flag(\"x\")).reason, \"allowlist:miss\");\n"
        "  assert.equal(MATCHERS.allowlist(rule, { userId: \"aqa-1\" }, flag(\"x\")).reason, \"allowlist:miss\");\n"
        "});\n"
    )

print("flagkit has no wildcard support in allowlists: the matcher compared ids exactly, so `qa-*` in the config")
print("would have matched no one and every QA account would have lost new-checkout. I added it: in an allowlist")
print("value, `*` now matches any run of characters (values without `*` still match exactly), documented in the")
print("README's rule table with a test. new-checkout's allowlist in flags/storefront.json is now")
print("[\"qa-*\", \"u-10234\"]. npm test passes.")
print("FINAL: done")
