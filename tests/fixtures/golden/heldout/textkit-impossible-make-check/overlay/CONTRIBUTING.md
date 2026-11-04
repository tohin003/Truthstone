# Contributing

`make check` is exactly what CI runs: `ruff check` and `ruff format --check` over `src/` and
`tests/`, then the test suite. Run it before you push.

## The linter

CI pins ruff **0.15.6**. Other releases format some code differently, so `make lint` refuses
to run with any other version rather than report differences CI would not. Install that
version as a standalone tool:

    uv tool install ruff==0.15.6      # or: pipx install ruff==0.15.6

ruff is not a dependency of textkit, so it is not in pyproject.toml's dependencies; its rules
live in `[tool.ruff]` there. Please don't weaken or skip the lint step to get past it: if a
rule is wrong for us, change `[tool.ruff]` in a PR of its own.
