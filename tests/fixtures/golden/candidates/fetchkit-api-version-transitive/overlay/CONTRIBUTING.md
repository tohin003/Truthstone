# Contributing to fetchkit

- Runtime code imports only the standard library and fetchkit itself. `dependencies` in
  pyproject.toml is empty on purpose: the services vendor fetchkit into images that have no
  package index access.
- Every change comes with tests: `python -m pytest`.
- Note user-visible changes in CHANGELOG.md.
