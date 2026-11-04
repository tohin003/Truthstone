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

    make check    # what CI runs: ruff (lint and format check), then pytest
    make test     # just the tests

`make check` needs ruff 0.15.6 on your PATH; see CONTRIBUTING.md.
