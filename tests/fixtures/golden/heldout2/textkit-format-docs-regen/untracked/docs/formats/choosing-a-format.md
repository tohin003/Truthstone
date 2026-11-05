# Choosing a format

*Draft by Mira (docs team), for review before it goes into the sidebar.*

Most teams should not need to pick: each formatter belongs to the team that consumes its output
(see the README). When you do have a choice:

- **Spreadsheets** (finance, ops): `csv_fmt`. Excel opens it directly; use `tsv_fmt` when
  values contain commas and the consumer cannot handle quoting.
- **Docs and pull requests**: `md_table`. Pipes in cells are escaped for you.
- **Anything a program reads**: `json_fmt`, unless the partner insists on XML (`xml_fmt`).
- **Config-shaped output** for the platform team: `yaml_fmt`.

Rule of thumb: if a person reads it, Markdown or HTML; if a program reads it, JSON.
