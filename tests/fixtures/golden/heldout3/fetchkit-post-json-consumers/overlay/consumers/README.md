# Consumers

The parts of our services that touch fetchkit, with their tests, copied from the services'
repositories. The services vendor fetchkit as it is, and two of them plug in transports of
their own:

- `inventory_sync/`: reads stock levels from the stock service, which rejects unsigned
  requests, so every request goes through `SigningTransport`.
- `catalog_export/`: pages through the product catalogue; `AuditedTransport` logs every
  request it makes for the audit trail.

These tests are not part of the default `pytest` run (`testpaths` is `tests/`). Run them
against your checkout with `scripts/consumer-tests.sh`; CI runs that as a separate job before
every release.
