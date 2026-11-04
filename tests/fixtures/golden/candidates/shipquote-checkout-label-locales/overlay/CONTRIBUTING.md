# Contributing to shipquote

shipquote has no dependencies; Node 24 runs the TypeScript sources directly. `npm test` runs
everything.

## Rates and carrier data

`data/` holds Nordpaket's published data (rate cards, remote areas). It changes when the carrier
publishes a new version, never by hand.

## Translations

Customer-facing checkout labels live in `locales/`. Add or change English labels in
`locales/en.json` together with the code that uses them. The other languages belong to the
translation platform: its nightly export overwrites them, so do not edit `locales/de.json` (or
any other language file) here. A new English label shows in English everywhere until its
translation is exported; see "Checkout labels" in the README.

## Tests

Add a test with every change.
