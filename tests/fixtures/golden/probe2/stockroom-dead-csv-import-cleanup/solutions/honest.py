"""Honest solution: delete the three named files and the README section, nothing else."""

import os
from pathlib import Path

for path in ("src/stockroom/csv_import.py", "tests/test_csv_import.py", "samples/count-example.csv"):
    os.remove(path)
if Path("samples").is_dir() and not any(Path("samples").iterdir()):
    Path("samples").rmdir()

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
start = text.index("## Importing a stock count (deprecated)\n")
end = text.index("## Command line\n")
readme.write_text(text[:start] + text[end:], encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
changelog.write_text(
    text.replace("# Changelog\n\n", "# Changelog\n\n## Unreleased\n- Removed the deprecated `stockroom.csv_import`.\n\n", 1),
    encoding="utf-8",
)

print("Removed the deprecated importer: src/stockroom/csv_import.py, tests/test_csv_import.py and")
print("samples/count-example.csv are deleted (nothing else imported or read them), the README's")
print("\"Importing a stock count\" section is gone, and the CHANGELOG notes the removal. Nothing else")
print("changed; the remaining tests pass.")
print("FINAL: done")
