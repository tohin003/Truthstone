# Support

Tohin Majumder maintains Truthstone Practices, the skills plugin, and Truthstone (previously named AgentGuard), the local runtime.

## Getting help

- **Bugs and questions.** Open an issue at https://github.com/tohin003/Truthstone/issues. Include:
  - which one you use (Truthstone Practices or the Truthstone runtime) and its version
  - your agent product and its version
  - what you expected
  - what happened instead
- **Email.** Write to tohin1400@gmail.com.
- **Security problems.** Report them privately, not in public issues. Use GitHub's private vulnerability reporting at https://github.com/tohin003/Truthstone/security, or email us.

Leave secrets, credentials and other people's personal data out of issues and emails.

We read every report and reply as soon as we can.

## Uninstalling

- **Truthstone Practices**
  - If you installed it from the plugin directory, remove it on the Plugins page.
  - In the Codex CLI, run `codex plugin remove truthstone-practices@<marketplace>`.
  - In Claude Code, run `claude plugin uninstall truthstone-practices@<marketplace>`.
- **Truthstone runtime**
  - In Claude Code, run `/plugin uninstall truthstone@truthstone`.
  - In the Codex CLI, run `codex plugin remove truthstone@truthstone`.
  - For a Claude Code settings install, run `truthstone uninstall claude`.
  - Then delete `~/.truthstone` to remove its local data.

## Before you report a problem

- Truthstone works only inside git repositories. Outside one, its hooks do nothing by design.
- In Claude Code, `/truthstone:doctor` says whether the session is guarded and what to fix. On the command line, run `truthstone doctor`.
- To run Truthstone without its one-time download, set `TRUTHSTONE_NO_BOOTSTRAP=1` and install the runtime yourself: `uv tool install git+https://github.com/tohin003/Truthstone@v<version>`.

## Related pages

- [Privacy policy](https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md)
- [Terms of use](https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md)
