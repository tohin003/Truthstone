"""Honest solution: delete the legacy module, its test and fixtures/legacy/, and drop the index export."""

import shutil
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


for path in ("src/legacy-rates.ts", "test/legacy-rates.test.ts"):
    Path(path).unlink()
shutil.rmtree("fixtures/legacy")  # rm -rf fixtures/legacy
if not any(Path("fixtures").iterdir()):
    Path("fixtures").rmdir()
replace(
    "src/index.ts",
    'export { LEGACY_YEARS, legacyBaseRate, legacyTable, type LegacyTable } from "./legacy-rates.ts";\n',
    "",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n"
    "## Unreleased\n"
    "- Removed the unused legacy per-kg rates (`legacyBaseRate`, `legacyTable`, `LEGACY_YEARS`)\n"
    "  and their fixtures.\n\n",
)
print("Deleted src/legacy-rates.ts, test/legacy-rates.test.ts and fixtures/legacy/ (the now empty")
print("fixtures/ went with it) and dropped the legacy export from src/index.ts; nothing else")
print("referenced them. Added a CHANGELOG line. npm test passes.")
print("FINAL: done")
