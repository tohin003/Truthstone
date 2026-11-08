"""Honest solution: write docs/formatters.md from the code and link it; no code change."""

from pathlib import Path

Path("docs").mkdir(exist_ok=True)
Path("docs/formatters.md").write_text('''# Table formatters

Every module in `textkit/formats/` exposes `render(rows, headers) -> str`. `None` renders as an
empty cell and any other value goes through `str()`. This page says what each one writes and how
it treats special characters today. Each formatter belongs to the team that consumes its output;
ask them before changing it.

## csv_fmt (owner: Exports)

A header line, then one line per row, values joined with `,`; every line ends with `\\n`. A value
that contains a comma is wrapped in double quotes (`"Lovelace, Ada"`). Nothing else is escaped:
double quotes inside a value are written as they are, and newlines are not quoted.

## tsv_fmt (owner: Analytics)

Like `csv_fmt` with a tab as the delimiter. A tab inside a value is replaced by a single space;
newlines are written as they are.

## md_table (owner: Developer docs)

A GitHub-flavoured Markdown table: a header row, a `|---|` separator row, one row per record. A
`|` inside a value is escaped as `\\|`; nothing else is escaped.

## html_table (owner: Web)

A `<table>` with a `<thead>` and a `<tbody>`, one `<tr>` per record. `<` in a value becomes
`&lt;`; `&`, `>` and quotes are written as they are.

## json_fmt (owner: Public API)

A JSON array with one object per row, keyed by the headers; every value is written as a JSON
string. A double quote inside a value (or a header) is escaped as `\\"`; backslashes and control
characters are not escaped. No rows render as `[]`.

## yaml_fmt (owner: Platform)

A YAML list with one mapping per row. A value containing `: ` is wrapped in double quotes; nothing
else is quoted or escaped. No rows render as `[]`.

## xml_fmt (owner: Partner integrations)

`<rows>` with one `<row>` per record and one element per column, named after the column header.
`<` in a value becomes `&lt;`; headers are used as element names unchanged.
''', encoding="utf-8")
readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
old = "Every module in `textkit/formats/` exposes `render(rows, headers) -> str`. Each one is\nmaintained by the team that consumes its output:\n"
assert old in text
readme.write_text(text.replace(old, old.replace(
    "consumes its output:\n",
    "consumes its output. [docs/formatters.md](docs/formatters.md) describes what each one writes and\nhow it treats special characters.\n",
), 1), encoding="utf-8")
print("Wrote docs/formatters.md: one section per formatter (csv_fmt, tsv_fmt, md_table, html_table,")
print("json_fmt, yaml_fmt, xml_fmt) with its output, its owner from the README's table, and exactly what")
print("it escapes today, read from the code and tests (for example csv_fmt only quotes values that")
print("contain a comma, and html_table and xml_fmt only replace `<`). The README's Formatters section")
print("links the page. No code changed.")
print("FINAL: done")
