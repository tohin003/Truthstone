# Truthstone checks

A small, stateless MCP server that gives a model a deterministic second opinion from
Truthstone's own rules. It is the optional tool half of the Truthstone Practices companion
plugin; the skills work without it.

| Tool | What it checks | Truthstone rule it calls |
| --- | --- | --- |
| `check_shell_command` | A command line, for destructive or irreversible effects (recursive deletes, force pushes, hard resets, `git clean`, download piped to a shell, `DROP TABLE`, block-device writes), with a guarded form where the rule has one | `validate.checks.risky_command`, `validate.modify.safer_form` |
| `check_test_edit` | A test file before and after a change, for skips, deleted tests, fewer assertions, changed expected values and run-around hooks (Python, JavaScript, TypeScript) | `validate.weakened_tests.weakenings` |
| `check_test_runs` | Edits and commands in order, for a whole-suite test run that passed after the last edit; flags failing, stale and narrowed runs, and (optionally) a final message that claims more | `verify.runners.outcome_from_result`, `verify.runners.assess_timeline`, `verify.claims.classify` |

Every tool is read-only: it reads the text it is given, runs nothing, fetches nothing and
stores nothing. The server does not log request bodies or tool arguments.

## Run it

```sh
pip install -r requirements.txt
uvicorn truthstone_checks:app --host 0.0.0.0 --port 8000
```

- `POST /mcp`: the MCP endpoint (Streamable HTTP, stateless, JSON responses, no authentication).
- `GET /` and `GET /healthz`: a one-line description.
- `GET /.well-known/openai-apps-challenge`: the value of the `OPENAI_APPS_CHALLENGE`
  environment variable as plain text, or 404 when it is unset (OpenAI domain verification).

Inputs are capped at 200,000 characters per call; request bodies at 1 MiB.

From a checkout of this repository, `uv run uvicorn truthstone_checks:app --app-dir
services/truthstone-checks` runs it against the local source instead, and
`uv run pytest tests/test_truthstone_checks.py` tests it.

## The public instance

The instance the directory plugin connects to runs on Vercel at
`https://truthstone-checks.vercel.app` (MCP endpoint `/mcp`). `app.py` is the entry point
Vercel's Python runtime loads, and `.python-version` pins the interpreter. Deploy from this
folder with `vercel deploy --prod`. The endpoint address cannot be changed after the plugin is
published in OpenAI's directory without contacting their support, so keep it stable.
