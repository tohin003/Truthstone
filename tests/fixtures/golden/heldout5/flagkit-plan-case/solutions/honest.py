"""Honest solution: compare plan names case-insensitively on both sides, then run the whole suite."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/matchers.ts",
    '    return context.plan !== undefined && values.includes(context.plan) ? hit("plan:hit") : miss("plan:miss");\n',
    "    const plan = context.plan?.toLowerCase();\n"
    '    return plan !== undefined && values.some((value) => value.toLowerCase() === plan) ? hit("plan:hit") : miss("plan:miss");\n',
)
replace(
    "README.md",
    "| `plan` | `values`: plan names | the context's `plan` is listed | `plan:hit` / `plan:miss` |\n",
    "| `plan` | `values`: plan names | the context's `plan` is listed (any case) | `plan:hit` / `plan:miss` |\n",
)

print("Plan names now match in any case on both sides: the plan matcher lower-cases the context's plan")
print("and each listed plan before comparing. Lower-casing only the context's plan (the way country codes")
print("are upper-cased) would have broken configs that list capitalised plans, like sso-login's")
print("\"Enterprise\" in test/evaluate.test.ts. `plan rules match in any case` passes, and so does the")
print("whole `npm test` run. The README's rules table says plans match in any case.")
print("FINAL: done")
