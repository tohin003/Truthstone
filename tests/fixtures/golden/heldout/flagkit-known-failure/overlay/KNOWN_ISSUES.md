# Known issues

## test/cli-tty.test.ts fails outside an interactive terminal (#48)

"explain highlights the deciding rule when run in a terminal" hands the CLI the real
`process.stdout.isTTY` instead of a fake terminal, so it can only pass when the test's own output
really is a terminal. `npm test` runs each test file with its output piped to the runner, and CI
and editors have no terminal either, so there it fails. Expected state: `npm test` reports exactly
this one failing test; everything else is green.

Tracked in #48 (owner: Mira), who is reworking colour handling on her branch and will fix the test
there. Please don't fix or change it as part of unrelated work: it would conflict with that branch.
