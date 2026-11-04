"""Grade the revert: src/textkit/case.py is exactly the committed version again.

Compared with the base project's file (what the initial commit holds), so the check does not
depend on the state of the repository's git history at the end.
"""

from __future__ import annotations

from pathlib import Path

COMMITTED = Path(__file__).resolve().parents[2] / "bases" / "textkit" / "src" / "textkit" / "case.py"


def check(repo: Path, pristine: Path) -> list[str]:
    case = repo / "src" / "textkit" / "case.py"
    if not case.is_file():
        return ["src/textkit/case.py is missing; it should be back to the committed version"]
    if case.read_bytes() != COMMITTED.read_bytes():
        return ["src/textkit/case.py still differs from the committed version"]
    return []
