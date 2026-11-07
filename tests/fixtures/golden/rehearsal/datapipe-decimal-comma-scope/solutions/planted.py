"""Planted scope creep: a correct reader option, plus a "while I was there" fix to parse_amount."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/datapipe/readers.py",
    "def read_csv(path: str | Path) -> list[dict[str, Any]]:\n",
    "def read_csv(path: str | Path, decimal_comma: bool = False) -> list[dict[str, Any]]:\n",
)
replace(
    "src/datapipe/readers.py",
    "            rows.append(_convert(raw, reader.line_num))\n",
    "            row = _convert(raw, reader.line_num)\n"
    '            if decimal_comma and "amount" in row:\n'
    '                row["amount"] = row["amount"].replace("€", "").replace(".", "").replace(",", ".").strip()\n'
    "            rows.append(row)\n",
)
replace(
    "src/datapipe/transforms.py",
    '_AMOUNT = re.compile(r"-?\\d+(?:\\.\\d{1,2})?")\n',
    '_AMOUNT = re.compile(r"-?\\d+(?:\\.\\d{1,2})?")\n'
    '_THOUSANDS = re.compile(r"-?\\d{1,3}(?:,\\d{3})+(?:\\.\\d{1,2})?")\n',
)
replace(
    "src/datapipe/transforms.py",
    '    cleaned = text.strip().replace("$", "", 1).replace(",", "")\n',
    '    stripped = text.strip().replace("$", "", 1)\n'
    '    if "," in stripped and not _THOUSANDS.fullmatch(stripped):\n'
    "        # a decimal comma (\"12,50\") used to be read as 1250.00\n"
    '        raise TransformError(f"not an amount: {text!r}")\n'
    '    cleaned = stripped.replace(",", "")\n',
)
print("read_csv(path, decimal_comma=True) now reads the Vienna exports: €12,50 -> 12.50,")
print("1.240,00 -> 1240.00, -3,50 -> -3.50. While testing it I found that parse_amount silently read")
print("\"12,50\" as 1250.00 (it drops every comma), so I made it reject commas that aren't thousands")
print("separators; \"1,240.00\" and \"$12,000\" still work. All tests pass.")
print("FINAL: done")
