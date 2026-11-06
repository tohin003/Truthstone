# Contributing

- Run `make check` before you push: it is exactly what CI runs. It runs the unit tests (what
  plain `pytest` runs, `testpaths` in pyproject.toml) and then `scripts/replay.py`, which sends
  the requests recorded at the staging gateway through `Client` and the real `UrllibTransport`
  and checks fetchkit's answers against the recordings in `recorded/`. The fake transport in
  `tests/conftest.py` only returns what a test scripts; the replay is how we see what the
  gateway really sends back.
- Recordings are captured by the platform team. Don't edit them by hand.
- Runtime code imports only the standard library (the README promises no runtime
  dependencies, and the services vendor fetchkit as is).
- Add a line to CHANGELOG.md for anything a caller would notice.
