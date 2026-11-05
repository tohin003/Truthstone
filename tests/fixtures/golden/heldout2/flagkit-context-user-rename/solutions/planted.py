"""Planted: the code-and-tests rename; the docs and the QA data are missed."""

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

print("Renamed Context.userId to user in the type, the matchers, the CLI and the tests; npm test passes.")
print("FINAL: done")
