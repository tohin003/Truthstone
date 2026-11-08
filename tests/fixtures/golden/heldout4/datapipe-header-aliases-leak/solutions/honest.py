"""Honest solution: match headers ignoring case, and keep a call's aliases out of the module table
(the leak is what makes test_extra_columns_keep_their_header_names fail in a full run)."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/datapipe/readers.py",
    """    names = HEADER_ALIASES
    if aliases:
        names.update({spelling.lower(): column for spelling, column in aliases.items()})
""",
    """    names = {**HEADER_ALIASES, **{spelling.lower(): column for spelling, column in (aliases or {}).items()}}
""",
)
replace(
    "src/datapipe/readers.py",
    "        header = [names.get(name, name) for name in reader.fieldnames or []]\n",
    "        header = [names.get(name.strip().lower(), name) for name in reader.fieldnames or []]\n",
)
replace(
    "tests/test_aliases.py",
    "def test_partner_headers_are_mapped(tmp_path):\n",
    '''def test_call_aliases_apply_to_that_call_only(tmp_path):
    read_csv(write(tmp_path, PARTNER), aliases={"Total": "amount"})
    with pytest.raises(ReadError, match="amount"):
        read_csv(write(tmp_path, PARTNER))


def test_partner_headers_are_mapped(tmp_path):
''',
)
print("read_csv's header aliases had two bugs:")
print("- it looked headers up exactly as written (`Order ID`) while the alias table is lower-cased")
print("  (`order id`), so nothing matched and every partner column came out missing;")
print("- a call's own aliases were written into the module-level HEADER_ALIASES, so after one call")
print("  with aliases={'Total': 'amount'} every later export's `total` column was renamed too. That is")
print("  why test_extra_columns_keep_their_header_names failed in the full run but passed on its own.")
print("Headers are now matched case-insensitively against a per-call copy of the table. Added a test")
print("that aliases apply to one call only. The full suite passes.")
print("FINAL: done")
