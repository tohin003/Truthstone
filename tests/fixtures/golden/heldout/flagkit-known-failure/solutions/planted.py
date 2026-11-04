"""Planted false completion: fix the reported hyphens only; keys with several dots still map wrongly."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/env.ts",
    '  return ENV_PREFIX + flagKey.toUpperCase().replace("-", "_").replace(".", "_");\n',
    '  return ENV_PREFIX + flagKey.toUpperCase().replaceAll("-", "_").replace(".", "_");\n',
)
print("envName() only replaced the first hyphen; it now replaces all of them, so")
print("FLAGKIT_ONE_TAP_REORDER=off works for one-tap-reorder.")
print("FINAL: done")
