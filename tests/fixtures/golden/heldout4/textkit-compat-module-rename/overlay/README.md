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
- `textkit.legacy_case`: the 0.x case helpers. The key renamer and the CLI's `labels` command and
  `human` style use them on purpose (they keep acronyms whole), and old callers still reach
  them as `textkit.camelize`, `textkit.underscore` and so on.
- `textkit.cli`: the `textkit` command (`textkit case`, `textkit slug`, `textkit labels`).

## Docs site filters

The docs site renders its templates with filters from textkit (`{{ page.title | title }}`,
`{{ column | label }}`). It finds them through the `docsite.filters` entry points declared in
`pyproject.toml`, so a filter is just a function named there.

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
