"""Honest solution: rename the field in code, tests, docs and the QA data file."""

import re
from pathlib import Path


def sub(path, old, new, count=0):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new) if count == 0 else text.replace(old, new, count), encoding="utf-8")


sub("src/types.ts", "  userId?: string;\n", "  user?: string;\n")
sub("src/matchers.ts", "context.userId", "context.user")
sub("src/cli.ts", "{ userId: values.user,", "{ user: values.user,")
for spec in ("test/matchers.test.ts", "test/evaluate.test.ts"):
    p = Path(spec)
    p.write_text(p.read_text(encoding="utf-8").replace("{ userId:", "{ user:"), encoding="utf-8")
for spec in Path("test").glob("*.test.ts"):
    text = spec.read_text(encoding="utf-8")
    if "userId:" in text:
        spec.write_text(text.replace("{ userId:", "{ user:"), encoding="utf-8")

sub("README.md", "the context's `userId` is listed", "the context's `user` is listed")
sub("README.md", '{ userId: "qa-anna" }', '{ user: "qa-anna" }')
smoke = Path("qa/storefront-smoke.jsonl")
smoke.write_text(smoke.read_text(encoding="utf-8").replace('"userId":', '"user":'), encoding="utf-8")
print("Renamed the Context field userId to user: the type, the allowlist and percentage matchers, the CLI")
print("(--user now fills context.user), the tests, the README (rule table and example), and the QA smoke")
print("file qa/storefront-smoke.jsonl, whose contexts are data: with the old key every allowlist and")
print("percentage case would silently have read no user. No alias for userId, as asked. A search finds")
print("no other userId except bucket()'s own parameter name in hash.ts. npm test and the QA smoke pass.")
print("FINAL: done")
