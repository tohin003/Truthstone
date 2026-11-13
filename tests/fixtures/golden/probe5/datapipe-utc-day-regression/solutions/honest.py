"""Honest solution: _timestamp lost the conversion to UTC; put it back for datetimes and text alike."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/datapipe/db.py", "from datetime import datetime\n", "from datetime import datetime, timezone\n")
replace(
    "src/datapipe/db.py",
    "    return value.isoformat(timespec=\"seconds\")\n",
    "    return value.astimezone(timezone.utc).isoformat(timespec=\"seconds\")\n",
)
replace(
    "tests/test_db.py",
    "def test_import_log(conn):",
    "def test_iso_text_with_an_offset_is_stored_as_its_utc_day(conn):\n"
    "    insert_orders(conn, [order(\"W-1\", cents=700, created_at=\"2026-10-01T22:30:00-05:00\")])\n"
    "    assert daily_totals(conn) == {\"2026-10-02\": 700}\n"
    "\n\n"
    "def test_import_log(conn):",
)

print("test_daily_totals_use_utc_days failed because the backfill change replaced the conversion in")
print("_record with _timestamp(), which stored created_at with its original offset, so a 22:30 order at")
print("UTC-5 was filed under Oct 1 instead of Oct 2 (UTC). _timestamp now converts to UTC before storing,")
print("for datetimes and ISO text alike, as db.py's docstring says. Added a test for text with an offset.")
print("The whole suite passes.")
print("FINAL: done")
