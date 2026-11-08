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

## Slugs are permanent

The docs site serves every page at the slug of its title and keeps no redirects; the search
index, the sitemap and plenty of other sites link to those URLs. So `slugify` never changes the
slug of an input once it has been released: the same text, `separator` and `max_length` give
the same slug in every version, and changing one silently breaks every link to that page. A new
rule may only change input that so far gave an empty slug (a title made only of symbols, such
as `"???"`). A page that needs a better URL gets one by hand, with `slug:` in its front matter;
slugify stays as it is.

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
