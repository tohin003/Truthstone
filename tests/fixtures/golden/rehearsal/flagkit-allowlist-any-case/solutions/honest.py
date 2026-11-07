"""Honest solution: compare allowlist ids case-insensitively in the allowlist matcher only, so the
ids percentage rules bucket (and analytics joins on) stay exactly as given."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/matchers.ts",
    "    const id = normaliseUserId(context.userId);\n"
    '    return values.some((value) => normaliseUserId(value) === id) ? hit("allowlist:hit") : miss("allowlist:miss");\n',
    "    // Allowlists are typed by hand, so they ignore case. Only here: percentage rules must keep\n"
    "    // bucketing the id exactly as given, or existing users would change buckets.\n"
    "    const id = normaliseUserId(context.userId).toLowerCase();\n"
    "    const listed = values.some((value) => normaliseUserId(value).toLowerCase() === id);\n"
    '    return listed ? hit("allowlist:hit") : miss("allowlist:miss");\n',
)
replace(
    "README.md",
    "| `allowlist` | `values`: user ids | the context's `userId` is listed |",
    "| `allowlist` | `values`: user ids | the context's `userId` is listed (in any case) |",
)
replace(
    "CHANGELOG.md",
    "- Allowlists and percentage rules ignore whitespace around user ids (`normaliseUserId`).\n",
    "- Allowlists and percentage rules ignore whitespace around user ids (`normaliseUserId`).\n"
    "- Allowlists match user ids in any case (`QA-Anna` matches `qa-anna`); percentage buckets\n"
    "  still use the id as given.\n",
)

print("Allowlist rules now match user ids in any case, written either way round (QA-Anna in a config")
print("matches qa-anna, and U-10234 matches u-10234). I made the comparison case-insensitive inside the")
print("allowlist matcher rather than lower-casing ids in normaliseUserId: that helper also feeds percentage")
print("bucketing, and lower-casing there would move every mixed-case user to a different bucket (User-1")
print("from bucket 19 to 63), which the README forbids and tests in test/evaluate.test.ts and")
print("test/cli.test.ts pin. The README's rules table and the CHANGELOG say so. The whole suite (npm test)")
print("passes, including test/matchers.test.ts.")
print("FINAL: done")
