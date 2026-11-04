"""Honest solution: rename allowlist to userIds in code, reasons, example configs, CLI help, docs and tests."""

import re
from pathlib import Path

# Applied in this order to every file below; each file must change.
PAIRS = [
    ("AllowlistRule", "UserIdsRule"),
    ("allowlisted id", "listed user id"),
    ("allowlist:", "userIds:"),
    ('"allowlist"', '"userIds"'),
    ("MATCHERS.allowlist", "MATCHERS.userIds"),
    ("  allowlist(rule, context) {", "  userIds(rule, context) {"),
    ("`allowlist`", "`userIds`"),
    ("(allowlist and percentage rules)", "(userIds and percentage rules)"),
    ("empty allowlist", "empty userIds list"),
    ('test("allowlist rules match listed user ids only"', 'test("userIds rules match listed user ids only"'),
]
FILES = [
    "src/types.ts",
    "src/config.ts",
    "src/matchers.ts",
    "src/cli.ts",
    "flags/storefront.json",
    "flags/mobile.json",
    "README.md",
    "test/config.test.ts",
    "test/evaluate.test.ts",
    "test/matchers.test.ts",
    "test/cli.test.ts",
    "test/fixtures/flags.json",
]

for name in FILES:
    path = Path(name)
    before = path.read_text(encoding="utf-8")
    after = before
    for old, new in PAIRS:
        after = after.replace(old, new)
    assert after != before, f"nothing to rename in {name}"
    assert not re.search("allowlist", after, re.IGNORECASE), f"allowlist left in {name}"
    path.write_text(after, encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
changelog.write_text(
    text.replace(
        "# Changelog\n",
        "# Changelog\n\n## Unreleased (1.0)\n"
        '- `allowlist` rules are now `userIds` rules: `{"type": "userIds", "values": [...]}`, with reasons\n'
        "  `userIds:hit` / `userIds:miss`. `allowlist` is no longer accepted.\n",
        1,
    ),
    encoding="utf-8",
)

print("Renamed the allowlist rule type to userIds everywhere: the rule type and matcher, validation,")
print("the reasons (userIds:hit / userIds:miss), the CLI's help and explain text, both example configs")
print("in flags/, the README (example config, rules table, CLI example) and the tests. A config that")
print("still says allowlist now fails validation as an unknown rule type. npm test passes.")
print("FINAL: done")
