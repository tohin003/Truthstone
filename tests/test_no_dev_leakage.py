"""No product code or product test may be keyed to a golden benchmark task.

ARCHITECTURE-v0.2 §6.2 rule 4. Scans ``src/`` and ``tests/`` (except the benchmark's own code,
tests and fixtures) for every golden task id and for strings unique to one task. The list is
kept only as hashes (``tests/fixtures/golden/leakage.json``, maintained by the benchmark builder
with ``python -m truthstone.bench.codex leakage --write``), so it cannot be read as a hint list.
A hit names the file, the line and the matched text, never the task.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from truthstone.bench.codex.leakage import MIN_LENGTH, digest, identifiers

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tests" / "fixtures" / "golden" / "leakage.json"
SCANNED = (ROOT / "src", ROOT / "tests")
EXCLUDED = (
    ROOT / "src" / "truthstone" / "bench",
    ROOT / "tests" / "bench",
    ROOT / "tests" / "fixtures",
    Path(__file__).resolve(),
)
SUFFIXES = {".py", ".ts", ".js", ".mjs", ".json", ".toml", ".md", ".txt", ".sh", ".yml", ".yaml"}
_HYPHENATED = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")


def _scanned_files() -> list[Path]:
    files = []
    for root in SCANNED:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES or "__pycache__" in path.parts:
                continue
            resolved = path.resolve()
            if any(resolved == ex or ex in resolved.parents for ex in EXCLUDED):
                continue
            files.append(path)
    return sorted(files)


def test_no_golden_task_id_or_task_unique_string_in_product_code_or_tests():
    data = json.loads(LIST.read_text(encoding="utf-8"))
    ids, strings = set(data["ids"]), set(data["strings"])
    assert ids and strings, "the leakage list is empty: regenerate it"
    hits = []
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for token in _HYPHENATED.findall(line.lower()):
                if digest(token) in ids:
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {token}")
            for token in identifiers(line):
                if len(token) >= MIN_LENGTH and digest(token) in strings:
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {token}")
    assert not hits, "benchmark task material in product code or tests:\n" + "\n".join(hits[:50])
