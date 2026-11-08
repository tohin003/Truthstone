# textkit

Small text utilities shared by the docs site and the export jobs.

```python
from textkit.case import title_case
from textkit.slug import slugify

slugify("Crème Brûlée Recipes")                 # "creme-brulee-recipes"
title_case("the art of computer programming")   # "The Art of Computer Programming"
```

## Modules

- `textkit.slug`: URL slugs.
- `textkit.case`: identifier case conversion (`to_snake`, `to_camel`, `to_kebab`) and `title_case`.
- `textkit.wrap`: plain-text wrapping.
- `textkit.stats`: word counts and reading time.
- `textkit.keys`: rename the keys of records between naming styles.
- `textkit.formats`: table renderers (CSV, TSV, Markdown, HTML, JSON, YAML, XML).
- `textkit.legacy_case`: the 0.x case helpers, still used by a few callers.
- `textkit.cli`: the `textkit` command (`textkit case`, `textkit slug`, `textkit labels`).

## Flattening records

The CSV and TSV exports need one column per value, so `textkit.keys` flattens nested records
into a single level, and turns flat ones back:

    flatten({"id": 7, "owner": {"name": "Ada"}, "tags": ["a", "b"]})
    # {"id": 7, "owner.name": "Ada", "tags.0": "a", "tags.1": "b"}

- `flatten(record, sep=".")` joins the keys on the way down with `sep`, at any depth. Lists
  are flattened by position (`tags.0`, `tags.1`, ...), mappings by key.
- An empty mapping or an empty list is kept as a value (`{"a": {}}` flattens to `{"a": {}}`),
  so nothing is lost.
- A key that contains `sep`, or a mapping key made only of the digits 0-9, could not be told
  apart from the structure after flattening: `flatten` raises `ValueError` naming that key.
- `unflatten(flat, sep=".")` reverses it, so `unflatten(flatten(record, sep), sep) == record`
  for every record `flatten` accepts. Under one parent, keys `0`, `1`, ... `n-1` become a list.
- Neither function changes its argument, and keys keep the record's order.

## Title case

Headings use title case. Every word is capitalised except the small words
(a, an, and, as, at, but, by, for, in, nor, of, on, or, the, to), which stay lowercase
unless they are the first or the last word of the title.

## Formatters

Every module in `textkit/formats/` exposes `render(rows, headers) -> str`. Each one is
maintained by the team that consumes its output:

| Module       | Owner                 |
| ------------ | --------------------- |
| `csv_fmt`    | Exports               |
| `tsv_fmt`    | Analytics             |
| `md_table`   | Developer docs        |
| `html_table` | Web                   |
| `json_fmt`   | Public API            |
| `yaml_fmt`   | Platform              |
| `xml_fmt`    | Partner integrations  |

## Development

    pip install -e '.[test]'
    python -m pytest

The `test` extra installs pytest and hypothesis (the property-based tests in
`tests/test_flatten.py`).
