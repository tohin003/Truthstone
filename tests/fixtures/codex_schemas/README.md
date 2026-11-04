# Codex hook schemas (vendored)

These JSON Schemas are copied unchanged from
`codex-rs/hooks/schema/generated/` in [openai/codex](https://github.com/openai/codex)
at tag `rust-v0.166.0` (commit `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`). They are the
release wire contract for Codex command hooks: one `*.input.schema.json` per event (the
JSON Codex writes to a hook's stdin) and one `*.output.schema.json` (what Codex accepts on
stdout). Every output schema sets `additionalProperties: false`: an unknown field makes
Codex reject the whole output. If it does, the hook fails open.

`tests/test_codex_contract.py` checks Truthstone's captured payloads
(`tests/fixtures/codex_payloads/`) against the input schemas and every output the Codex
adapter can produce against the output schemas. Re-vendor these files when the supported
Codex version changes.

openai/codex is licensed under the Apache License 2.0, the same license as Truthstone.
