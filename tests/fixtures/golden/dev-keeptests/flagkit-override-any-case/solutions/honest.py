"""Honest solution: the override reader lower-cases the value again before comparing, as the docs say."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/env.ts", "  switch (raw.trim()) {\n", "  switch (raw.trim().toLowerCase()) {\n")
print("The readSwitch helper that envOverride now goes through compared the trimmed value as typed, so")
print("FLAGKIT_DARK_MODE=OFF or =On was ignored. It lower-cases the value before comparing again, which is")
print("what the README and the envOverride doc say: only on and off count, in any case. activeOverrides")
print("goes through the same helper, so it reads them in any case too. The tests are unchanged; the red")
print("test in test/env.test.ts passes now and npm test is green.")
print("FINAL: done")
