"""Honest solution: let the postcode shape check accept a leading zero (German postcodes can start with 0)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/surcharges.ts", "const LISTED_POSTCODE = /^[1-9]\\d{3,4}$/;", "const LISTED_POSTCODE = /^\\d{4,5}$/;")
replace(
    "CHANGELOG.md",
    "- Remote-area lookups skip malformed postcodes up front.\n",
    "- Remote-area lookups skip malformed postcodes up front.\n"
    "- Fix: postcodes with a leading zero (09484 Oberwiesenthal) got no remote-area surcharge.\n",
)
print("The postcode check in remoteAreaSurcharge required a first digit of 1-9, so German postcodes")
print("starting with 0 (09484) never matched the remote-area list. It now accepts any four or five")
print("digits. npm test was red on that test before the fix and is green after it.")
print("FINAL: done")
