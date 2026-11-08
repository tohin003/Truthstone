# Contributing to shipquote

- shipquote has no npm dependencies, runtime or dev, and it stays that way: the checkout service
  copies `src/` into its own build and runs it on locked-down machines with no registry access.
  Use what Node itself provides.
- Node 24 runs the TypeScript sources directly (type stripping), so only erasable syntax: no
  `enum`, no `namespace`, no parameter properties.
- Every rule a quote or a booking follows is described in the README; change the README with the
  rule.
- Tests use `node:test` and live in `test/`; `npm test` runs them all.
