# AgentGuard Practices

AgentGuard Practices is a set of six instruction-only skills for coding agents. Each skill is a step-by-step protocol the agent follows at a specific point in a task:

- before reporting work as done
- before relying on code it has not seen
- before editing outside the request
- when sizing a plan
- before running an irreversible shell command
- before handing over a diff

The plugin contains Markdown instructions, icons and manifests, and nothing else. It has no executable code, no hooks and no MCP server. It does not run anything, connect to any service, or collect or send data.

The agent carries out each protocol with the tools it already has, such as reading files, searching the repository and running your project's own tests. It does this under your usual approval settings.

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

- **Codex CLI.** Run `codex plugin marketplace add tohin003/AgentGuard`, then `codex plugin add agentguard-practices@<marketplace>`. The first command prints the marketplace name.
- **Claude Code.** Inside a session, run `/plugin install agentguard-practices --marketplace tohin003/AgentGuard` (Claude Code 2.1.275 or later). On older versions, run `claude plugin marketplace add tohin003/AgentGuard`, then `claude plugin install agentguard-practices@<marketplace>`.
- **One session, without installing.** From a clone of this repository, run `claude --plugin-dir ./plugins/agentguard-practices`.

## What this plugin does not do

- **It does not enforce anything.** The skills are guidance that the model follows. They cannot block a command or a reply.
- **It does not include AgentGuard's deterministic checks.** Those come from AgentGuard, the open-source runtime in this repository, which uses local lifecycle hooks. AgentGuard is installed separately and is not part of this plugin.

## Stable skill names

The six skill names above are stable identifiers. Other tools may refer to a skill by its name, so renaming a skill counts as a breaking change.

## Privacy, terms and support

- [Privacy policy](https://github.com/tohin003/AgentGuard/blob/master/docs/legal/PRIVACY.md): this plugin collects nothing.
- [Terms](https://github.com/tohin003/AgentGuard/blob/master/docs/legal/TERMS.md)
- [Support](https://github.com/tohin003/AgentGuard/blob/master/docs/legal/SUPPORT.md)
- [Security policy](SECURITY.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
