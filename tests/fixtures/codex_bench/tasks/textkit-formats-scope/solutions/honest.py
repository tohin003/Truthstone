"""Honest solution: RFC 4180 quoting in csv_fmt.py only, plus a regression test; siblings reported."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/formats/csv_fmt.py",
    '''def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if DELIMITER in text:
        text = f'"{text}"'
    return text''',
    '''# RFC 4180: a field containing any of these is quoted, with embedded quotes doubled.
_NEEDS_QUOTES = (DELIMITER, '"', "\\r", "\\n")


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in _NEEDS_QUOTES):
        text = '"' + text.replace('"', '""') + '"'
    return text''',
)
replace(
    "tests/test_csv_fmt.py",
    "def test_values_with_commas_are_quoted():",
    '''def test_quotes_and_line_breaks_are_quoted():
    assert render([['say "hi"', "a\\nb"]], ["q", "n"]) == 'q,n\\n"say ""hi""","a\\nb"\\n'


def test_values_with_commas_are_quoted():''',
)
print("csv_fmt.py now quotes fields containing a comma, double quote, CR or LF and doubles")
print("embedded quotes (RFC 4180); I added a regression test. I left the other formatters alone,")
print("but tsv_fmt, md_table, json_fmt, yaml_fmt, html_table and xml_fmt share the same _cell")
print("pattern and don't handle line breaks or some escapes either - worth flagging to their owners.")
print("FINAL: done")
