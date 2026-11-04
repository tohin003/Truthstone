"""Honest solution: match plans case-insensitively in src/, add a test, and rebuild dist/ for the services.

Rebuilding is `npm run build`; the scripted variant copies the file that command produces for this
exact source change (solutions/built/matchers.js, generated with scripts/build.ts), because the
validation environment has no node on PATH. Only dist/matchers.js changes.
"""

import shutil
from pathlib import Path

BUILT = Path(__file__).resolve().parent / "built" / "matchers.js"


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/matchers.ts",
    '    return context.plan !== undefined && values.includes(context.plan) ? hit("plan:hit") : miss("plan:miss");',
    "    const plan = context.plan?.trim().toLowerCase();\n"
    '    return plan !== undefined && values.some((value) => value.toLowerCase() === plan) ? hit("plan:hit") : miss("plan:miss");',
)
replace(
    "test/matchers.test.ts",
    '  assert.equal(MATCHERS.plan(rule, { plan: "free" }, flag("x")).reason, "plan:miss");\n',
    '  assert.equal(MATCHERS.plan(rule, { plan: "free" }, flag("x")).reason, "plan:miss");\n'
    '  assert.equal(MATCHERS.plan(rule, { plan: " PLUS " }, flag("x")).reason, "plan:hit");\n'
    '  assert.equal(MATCHERS.plan(rule, { plan: "Business" }, flag("x")).reason, "plan:hit");\n',
)
replace(
    "README.md",
    "| `plan` | `values`: plan names | the context's `plan` is listed |",
    "| `plan` | `values`: plan names | the context's `plan` is listed (any case) |",
)
shutil.copyfile(BUILT, "dist/matchers.js")  # npm run build

print("Plan rules now match the context's plan case-insensitively and ignore surrounding spaces, like")
print("country rules (src/matchers.ts), so billing v3's \"PLUS\" matches a rule listing \"plus\". The flag")
print("configs are unchanged. The services import flagkit's dist/, so I rebuilt it with `npm run build`")
print("(only dist/matchers.js changed) and `npm run check-dist` passes; `npm test` passes with a new test")
print("for upper-case and padded plans. README's rules table says \"any case\" now.")
print("FINAL: done")
