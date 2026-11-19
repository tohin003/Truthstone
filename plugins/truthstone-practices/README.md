# Truthstone Practices

Truthstone Practices is a set of six skills for coding agents. Each skill is a step-by-step protocol the agent follows at a specific point in a task:

- before reporting work as done
- before relying on code it has not seen
- before editing outside the request
- when sizing a plan
- before running an irreversible shell command
- before handing over a diff

The plugin contains Markdown instructions with YAML display metadata, icons, manifests, its licence and security policy; nothing else. It has no executable code and no hooks, and it does not run anything or collect data itself.

The agent carries out each protocol with the tools it already has, such as reading files, searching the repository and running your project's own tests. It does this under your usual approval settings.

## Optional: Truthstone checks

The edition in the ChatGPT and Codex plugin directory also connects one remote MCP server, Truthstone checks. Its three read-only tools apply Truthstone's deterministic rules to text the model passes in, and three skills use them when they are available:

| Tool | Used by | What it checks |
|---|---|---|
| `check_shell_command` | `safe-shell` | A command line, for destructive or irreversible effects such as recursive deletes, force pushes and hard resets, with a guarded form where one exists |
| `check_test_edit` | `diff-review` | A test file before and after a change, for added skips, deleted tests, fewer assertions and changed expected values |
| `check_test_runs` | `evidence-before-done` | The task's edits and commands in order, for a whole-suite test run that passed after the last edit, and a final message that claims more than the runs show |

The tools receive only the text they are given (a command line, a test file's before and after, a list of commands with exit codes and output, optionally a message). They run nothing and store nothing. Without them, for example when the plugin is installed from this repository, every skill works as written. The server's source is in [`services/truthstone-checks`](https://github.com/tohin003/Truthstone/tree/master/services/truthstone-checks).

## Skills

| Skill | When it applies | What the agent does |
|---|---|---|
| `evidence-before-done` | Before saying a task is done, fixed or passing | Builds a requirement ledger from your request, including prohibitions such as "don't edit the tests". Ties each item to evidence gathered after the last edit. Reports each item as verified, failed or not verified |
| `ground-claims` | Before relying on a function, method, module, file, config key, route or package | Verifies that it exists and cites `file:line`. Says what does exist when something is missing, and labels unverified assumptions |
| `scope-discipline` | At the start of a task, and before editing outside it | States the expected scope, asks before out-of-scope edits, and follows existing conventions for file placement and naming |
| `proportional-planning` | At the start of a task | Sizes the plan to complexity and risk. Mechanical changes stay direct. Cross-service, security, data, public-interface and open-ended work gets investigated first |
| `safe-shell` | Before an irreversible command | Runs a pre-flight covering the exact target, reversibility, a safer alternative, and your explicit go-ahead for anything irreversible |
| `diff-review` | Before committing, opening a pull request or finishing | Compares the complete diff with the request, looking for missing requirements, unrequested changes, stale references, weakened tests and unexplained dependencies |

Each skill works on its own. Your instructions, and your repository's agent instructions such as `AGENTS.md`, always take priority over the skills.

## Install

Install from this repository's plugin marketplace:

- **Codex CLI.** Run `codex plugin marketplace add tohin003/Truthstone`, then `codex plugin add truthstone-practices@truthstone`.
- **Claude Code.** Inside a session, run `/plugin install truthstone-practices --marketplace tohin003/Truthstone` (Claude Code 2.1.275 or later). On older versions, run `claude plugin marketplace add tohin003/Truthstone`, then `claude plugin install truthstone-practices@truthstone`.
- **One session, without installing.** From a clone of this repository, run `claude --plugin-dir ./plugins/truthstone-practices`.

## What this plugin does not do

- **It does not enforce anything.** The skills are guidance that the model follows. They cannot block a command or a reply.
- **It does not include Truthstone's deterministic checks.** Those come from Truthstone (previously named AgentGuard), the open-source runtime in this repository, which uses local lifecycle hooks. Truthstone is installed separately and is not part of this plugin.

## Stable skill names

The six skill names above are stable identifiers. Other tools may refer to a skill by its name, so renaming a skill counts as a breaking change.

## Privacy, terms and support

- [Privacy policy](https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md): the skills collect nothing; the optional checks process the text they are given in memory and keep none of it.
- [Terms](https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md)
- [Support](https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md)
- [Security policy](SECURITY.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
