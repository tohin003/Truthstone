# Renaming the product

**Decided 2026-11-04:** AgentGuard is renamed **Truthstone**. In prose, write it as the user
asked: "Truthstone (previously named AgentGuard)" on first mention, plain "Truthstone" after
that.

The rename is one command, `scripts/rename_product.py`, followed by a review of the staged
diff. The tool is name-agnostic and deterministic: it reads the tree, never a list of files,
so the same command works on the final integrated tree and on every worker branch. This
document records what it changes, the compatibility decisions that need your sign-off, and
the steps no tool can take.

## The command

```bash
python3 scripts/rename_product.py --from AgentGuard --to Truthstone --dry-run   # the plan
python3 scripts/rename_product.py --from AgentGuard --to Truthstone             # do it, staged

uv sync --all-extras
TRUTHSTONE_HOME="$(mktemp -d)" .venv/bin/pytest -o addopts="" -q -p no:warnings
AGENTGUARD_HOME="$(mktemp -d)" .venv/bin/pytest -o addopts="" -q -p no:warnings  # old names still work
.venv/bin/ruff check src tests scripts/rename_product.py
python3 scripts/rename_product.py --from AgentGuard --to Truthstone --validate   # plugin validators
python3 scripts/rename_product.py --from AgentGuard --to Truthstone --audit      # what is left of the old name
git diff --cached -M --stat
```

It refuses a dirty tree (`--allow-untracked` tolerates untracked files) and a new name that
Python sources already use (`--force` overrides); earlier occurrences anywhere else are listed
for review: the release workflow already names `truthstone` on PyPI. It commits nothing, and
exits 0 when everything is clean, 1 when something needs attention, 2 when it refused.
`--previously NAME` changes the name in "(previously named NAME)" (default: the `--from` name);
`--no-previously` skips that step. `--lower`, `--upper` and `--kebab` override the derived
spellings. `--skip-tools` and `--skip-lock` are for scratch runs.

A real run does this, in order:

1. **Delegated renames.** A package that renames itself goes first. The skills companion's
   `scripts/companion_package.py` documents `rename --slug NEW --display ...`, so the tool
   calls it (`--slug truthstone-practices --display "Truthstone Practices" --developer ...
   --repo tohin003/Truthstone --also AgentGuard=Truthstone ...`). It edits its manifest, README,
   SECURITY.md, docs/LISTING.md and docs/legal, moves its directory, syncs its derived Claude
   manifest and checks itself. The generic pass then covers whatever it left.
2. **Text.** Every spelling of the old name in tracked text files is rewritten in one pass:
   `AgentGuard`, `agentguard`, `AGENTGUARD`, and the derived `agent-guard`, `agent_guard`,
   `AGENT_GUARD`, `Agent Guard`, `Agentguard` (the last five occur nowhere today). Spellings no
   rule covers, such as `AGENTguard`, are listed for a human.
3. **Paths.** Every tracked path containing the old name moves with `git mv`: whole
   directories where possible (`src/agentguard/`, `plugins/agentguard/`,
   `plugins/agentguard-claude/`), single files otherwise (`hooks/agentguard-hook.sh`,
   `assets/agentguard-logo.svg`).
4. **Former names.** The old name is recorded in every former-names registry: the
   `former-names` keep block in `src/truthstone/names.py`, and its mirror in
   `adapters/claude_code/forward.py`, which runs as `python -I -S` and cannot import the package.
   Those entries are the whole compatibility layer (next section).
5. **Prose.** The first plain mention in each user-facing document becomes
   "Truthstone (previously named AgentGuard)", and the README gains a "Renamed from AgentGuard"
   section (see below).
6. **Special files.** `.gitignore` keeps `.agentguard/` beside the new `.truthstone/`. Hand-written
   shell scripts (`plugins/truthstone-claude/scripts/*.sh`) get fallback lines for each
   `TRUTHSTONE_*` setting they read.
7. **Generators and checks.** Every module whose source documents
   `python -m <module> --write` is run (today: `truthstone.adapters.codex.plugin`, which writes
   the Codex manifest, hooks, launcher and marketplace entry) and then re-checked. Pinned
   values are recomputed (the Codex trust hashes in `tests/test_codex_plugin.py`), imports are
   re-sorted with `ruff --select I`, and `uv.lock` is regenerated with `uv lock`. Then the plugin
   validators run, each with throwaway `HOME`, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`:
   `claude plugin validate --strict` on `.` and on every plugin with a `.claude-plugin`,
   `codex plugin marketplace add <repo>` plus `codex plugin list` (it must list every plugin in
   `.agents/plugins/marketplace.json`), and the companion's `check`.
8. **Stage and audit.** Everything is staged. Every remaining spelling of the old name is
   classified (compatibility, historical record, "previously named" phrase, rename tooling) or
   reported as UNEXPECTED, and every place that reads a `TRUTHSTONE_*` setting without the
   former-name fallback is listed.

### What changes, by kind

| Kind | Before | After |
|---|---|---|
| Python package | `src/agentguard`, `import agentguard`, `python -m agentguard.cli.main` | `src/truthstone`, `import truthstone`, `python -m truthstone.cli.main` |
| Distribution, console scripts | `agentguard`, `agentguard-hook`, `agentguard-codex-hook` | `truthstone`, `truthstone-hook`, `truthstone-codex-hook` (uv.lock via `uv lock`) |
| Environment | `AGENTGUARD_HOME`, `_DISABLE`, `_OBSERVE`, `_START_TIMEOUT`, `_CODEX_HOOK`, `_NO_BOOTSTRAP`, `_SOURCE`, `_RUNTIME_SPEC`, `_UV`, `_INSTALL_WAIT`, `_PLUGIN_DATA` | `TRUTHSTONE_*`; the old names still work |
| Data | `~/.agentguard/agentguard.db`, per-workspace `.agentguard/` | `~/.truthstone/truthstone.db`, `.truthstone/` (old ones still used, see below) |
| Codex plugin | `agentguard@agentguard`, `plugins/agentguard`, `hooks/agentguard-hook.sh` | `truthstone@truthstone`, `plugins/truthstone`, `hooks/truthstone-hook.sh` |
| Claude Code plugin | `agentguard@agentguard`, `plugins/agentguard-claude`, `/agentguard:doctor` | `truthstone@truthstone`, `plugins/truthstone-claude`, `/truthstone:doctor` |
| Skills companion | `agentguard-practices`, "AgentGuard Practices" | `truthstone-practices`, "Truthstone Practices" |
| Ownership markers | `X-AgentGuard`, `agentguard.adapters.*` in hook commands | `X-Truthstone`, `truthstone.adapters.*`; old ones still recognised |
| URLs | `https://github.com/tohin003/AgentGuard` | `https://github.com/tohin003/Truthstone` |
| Prose | "AgentGuard" | "Truthstone (previously named AgentGuard)" on first mention, then "Truthstone" |

### What stays as written

Historical records describe what happened under the name it happened under, so they are
kept byte for byte, without annotation:

- the SPEC, `AgentGuard — Host-Powered AI Agent Reliability & Reasoning Layer.md` (file name,
  title and body), and the two planning documents written under the old name
  (`AgentGuard-ACT-II-Local_semantic-memory.md`, `AgentGuard-memory&database-management-plan.md`);
- `PROGRESS.md`, the dated benchmark and validation reports (`docs/BENCH-*.md`,
  `docs/VALIDATION-*.md`), the raw benchmark data (`docs/bench-*.json`);
- payloads captured from real sessions (`tests/fixtures/hook_payloads/`, `codex_payloads/`);
- the "Evidence" section of `docs/CODEX.md` (transcripts of live runs).

References to those files keep their names, so they still resolve (the SPEC's file name in
`IMPLEMENTATION_PLAN.md` and in `tests/spec/test_s03_failure_census.py`). To treat any of them
as living text, take its pattern out of `DEFAULT_POLICY["historical"]`; to add a one-line
"renamed since" note to each record instead, set `"mark_historical": True`.

Never touched: binary files (their names are reported if they contain the old name), `.git`,
`.venv` and anything untracked, the rename's own files (`scripts/rename_product.py`,
`tests/test_rename_tool.py`, this document), and `/Users/xyx/Projects/pebble`, which vendors a
snapshot of its own.

## Compatibility decisions: please confirm

All of them live in one place, `src/truthstone/names.py`. Before the rename its registry of
former names is empty and nothing behaves differently; the rename adds
`("AgentGuard", "agentguard", "AGENTGUARD")`. The tests in `tests/test_names.py` use a synthetic
former name, so they hold before and after.

1. **Environment variables: old names are fallbacks, indefinitely.** `names.env("TRUTHSTONE_X")`
   reads `TRUTHSTONE_X`, then `AGENTGUARD_X`; the first non-empty value wins, so an old setting
   keeps working and never overrides a new one. Shell launchers carry the same rule as POSIX
   lines, `[ -n "${TRUTHSTONE_X:-}" ] || [ -z "${AGENTGUARD_X+x}" ] || TRUTHSTONE_X=$AGENTGUARD_X`,
   which also keeps an unset setting unset (the Claude launcher tests `${..._UV+set}`).
   `truthstone doctor` says which old variables are set and their new names; nothing warns at
   run time. This is what keeps Pebble working: it sets `AGENTGUARD_HOME` at run time.
2. **Data directory: the old one stays in use until you move it.** `$TRUTHSTONE_HOME`, else
   `$AGENTGUARD_HOME`, else `~/.truthstone` if it exists, else `~/.agentguard` if it exists, else
   `~/.truthstone`. The database follows the same rule inside it (`truthstone.db`, else an
   existing `agentguard.db`), so an existing install never loses its data and nothing is
   moved automatically. `truthstone doctor` prints the move:
   `truthstone daemon stop && mv ~/.agentguard ~/.truthstone`. The per-workspace `.agentguard/`
   directory stays ignored by git and by the repository index.
3. **Hook entries written by the old name are recognised.** Claude settings hooks (the
   `X-AgentGuard` header, the `agentguard.adapters.claude_code.shim` command), Codex hooks (the
   `agentguard.adapters.codex.hook` command and the file description), Codex plugin hooks
   (`agentguard@agentguard`) and Claude plugin installs are all treated as ours:
   `truthstone install claude|codex` replaces them, `truthstone uninstall` removes them, and
   doctor points them out, as it does an old Codex plugin still installed. Without this,
   upgraded users would get every hook twice.
4. **No old command or import aliases.** `truthstone` is a new distribution; it ships no
   `agentguard` console scripts and no `agentguard` module. Old hook entries keep running the
   old install until `truthstone install …` replaces them.
5. **Wire names between a hook process and the daemon** (for example the session-mode
   pseudo-event) are renamed outright: both ends always come from one install.
6. **Codex trust is re-earned.** Codex binds trust to the plugin's id and contents; a renamed
   plugin is a new plugin, so every user reviews its hooks in `/hooks` once, whatever we do.
   The pins in `tests/test_codex_plugin.py` are recomputed with `tests/codex_trust.py` and
   marked as such; confirm them against a live `hooks/list` before release.

## "Truthstone (previously named AgentGuard)"

The first plain mention of the new name in each user-facing document becomes "Truthstone
(previously named AgentGuard)"; later mentions stay plain. Where (`DEFAULT_POLICY["previously"]`):

- Markdown: `README.md`, `docs/CODEX.md`, `docs/CLAUDE-PLUGIN.md`, `docs/LISTING.md`,
  `docs/legal/*.md`, plugin READMEs and every `SKILL.md` (its front-matter `description` counts);
- listing copy, per field because each is shown on its own: `description` in every plugin
  manifest and marketplace, `longDescription` in Codex manifests. The Codex plugin's manifest is
  generated, so its source constant (`LONG_DESCRIPTION` in `adapters/codex/plugin.py`) is
  annotated instead, and a line the phrase makes too long is re-wrapped.

A plain mention is prose: not code, not a quote (`> ...`) or table row (they reproduce text
verbatim), not a URL, path, identifier, possessive or compound name ("Truthstone Practices",
"Truthstone's"), and not a heading, unless the heading is the bare name (so the README's title
carries it). `displayName`, `shortDescription` (both capped at 30 characters) and CLI help
never do. A document that already says "previously named AgentGuard" is left alone, and the
tool never rewrites a "(previously named …)" phrase, so re-runs change nothing.

The README also gets a "Renamed from AgentGuard" section before its first section heading,
summarising decisions 1 to 4 for users.

## Running it on other branches

The output depends only on the tree and the arguments, so:

- on an already renamed tree it prints "Nothing to do" and exits 0;
- on a branch that gained code under the old name it renames just that code;
- on a branch with no former-names registry it still renames, with a warning: the
  compatibility layer arrives with the merge.

Recommended flow for a worker branch (core fixes, benchmark harness): merge `rename-tool`
(integration plus the compatibility layer and this tool, i.e. `rename/truthstone` minus its last
commit), run the same command, commit, then merge into `rename/truthstone`. Both sides then
went through the same transformation, so merges conflict only where real edits overlap.
Always pass the same arguments; `--previously` defaults to the `--from` name.

## Manual steps that remain

These need accounts or approval, so the tool leaves them:

1. **Rename the GitHub repository** `tohin003/AgentGuard` to `tohin003/Truthstone`. GitHub
   redirects the old URL, but the plugins' runtime sources
   (`git+https://github.com/tohin003/Truthstone@v<version>` in the Codex launcher and in the
   Claude plugin's `session-start.sh`) only work once the new name exists, and the `v<version>` release
   tags must be pushed there before any plugin version is published.
2. **Claim the package names**: `truthstone` on PyPI (and on npm, if a package is ever
   published there). Check availability before announcing. Once on PyPI, the runtime sources
   switch to a requirement (`truthstone==<version>`), as the comments beside `RUNTIME_SOURCE`
   in `adapters/codex/plugin.py` and `SOURCE_TEMPLATE` in `session-start.sh` say.
3. **Rename the local folder** `/Users/xyx/Projects/AgentGuard`, and update anything that names
   it (the Claude project directory, CLAUDE.md notes, scripts).
4. **Move existing installs** (yours first: `~/.local/share/uv/tools/agentguard`):
   `uv tool install` the new package, `truthstone install claude` / `truthstone install codex`
   to replace the old hooks, `codex plugin remove agentguard@agentguard` and
   `/plugin uninstall agentguard@agentguard` before adding the new plugins, and optionally
   `truthstone daemon stop && mv ~/.agentguard ~/.truthstone`.
5. **Pebble**, when it next re-vendors: update its imports, and the places that name
   `agentguard.db` directly (its retention code and validation scripts). An existing Pebble
   home keeps its `agentguard.db`; a new one gets `truthstone.db`. `AGENTGUARD_HOME` keeps
   working.
6. **Re-confirm the Codex trust pins** with a live `hooks/list`, and refresh the example hashes
   in `docs/CODEX.md` if they should match.
7. **Rebuild binary artifacts**: the companion ZIP (`python3 scripts/companion_package.py
   build`), and check that no image (`plugins/*/assets/*.png`) shows the old name.

## How the tool decides (for whoever extends it)

Everything is discovered from the tree, never listed by file:

- **registries**: any living file with a `rename-tool: keep-begin former-names` block holding
  one tuple assignment;
- **generators**: any module whose source says `python -m <module> --write`;
- **delegates**: any script that documents `python3 <script> rename --slug NEW --display ...`,
  and its `check` if it documents one;
- **plugin validators**: `.claude-plugin/marketplace.json`, every `*/.claude-plugin/plugin.json`,
  and `.agents/plugins/marketplace.json`.

The policy at the top of the script holds the rest, as path patterns: historical records and
sections, excluded files, lockfiles and their commands, pinned values and how to recompute them,
and the "previously named" targets. Two pragmas, `rename-tool: keep` on a line or a
`keep-begin`/`keep-end` block, protect text from any rename; the registries, the generated shell
fallbacks and the README's rename section use them.
