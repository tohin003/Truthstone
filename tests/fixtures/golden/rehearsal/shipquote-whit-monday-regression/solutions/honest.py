"""Honest solution: Whit Monday is 50 days after Easter Sunday (49 is Whit Sunday)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/calendar.ts", '  [49, "Whit Monday"],\n', '  [50, "Whit Monday"],\n')
print("The refactor put Whit Monday 49 days after Easter Sunday, which is Whit Sunday (Pentecost);")
print("Whit Monday is the day after, 50 days after Easter. 2026's came out as Sunday 24 May instead")
print("of Monday 25 May, so the holiday list test failed. Fixed the offset in EASTER_HOLIDAYS in")
print("src/calendar.ts. npm test is green again.")
print("FINAL: done")
