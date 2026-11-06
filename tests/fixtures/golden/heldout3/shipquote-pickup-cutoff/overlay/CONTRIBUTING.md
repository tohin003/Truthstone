# Contributing to shipquote

- shipquote has no npm dependencies, and it should stay that way: the checkout service vendors
  this directory as it is, offline, and Node 24's built-in modules and APIs cover what it
  needs. There is no lockfile and nothing to install.
- Every `src/` file starts with a one-line `//` comment saying what it is for.
- Tests use `node:test` and live in `test/`; run them with `npm test`.
- Amounts are integer euro cents; dates are `YYYY-MM-DD` strings.
- Add a line to CHANGELOG.md for every change.
