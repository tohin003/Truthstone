# Contributing to fetchkit

- Run `scripts/check.sh` before you push: it is exactly what CI runs. It runs the unit tests
  (`tests/`) and then the replay suite (`replay/`). A plain `python -m pytest` runs only the
  unit tests (`testpaths` in pyproject.toml).
- The unit tests use a fake transport with tidy, hand-written responses. The replay suite uses
  exchanges recorded in production (`replay/recordings/`, one JSON file per exchange, bodies
  byte for byte), played through `UrllibTransport` with `urlopen` stubbed out. It is the suite
  that shows how a change copes with what servers really send.
- fetchkit has no runtime dependencies; keep it that way.
- Add a CHANGELOG entry for anything a caller would notice.
