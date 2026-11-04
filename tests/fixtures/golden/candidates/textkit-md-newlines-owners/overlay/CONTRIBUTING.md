# Contributing to textkit

textkit has no runtime dependencies; please keep it that way.

## Formatters

Each module in `src/textkit/formats/` renders one format for one consuming team (see the
owners table in the README), and its exact output is that team's contract: their importers,
spreadsheets and pages depend on it byte for byte. Change a formatter only for its owners, in a
pull request they review. If you notice a problem in another team's formatter, open an issue for
them rather than fixing it in your change.

## Tests

`python -m pytest` runs everything. Add a test with every fix.
