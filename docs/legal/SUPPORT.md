# Support

{{PUBLISHER_NAME}} maintains AgentGuard Practices, the skills plugin, and AgentGuard, the local runtime.

## Getting help

- **Bugs and questions.** Open an issue at https://github.com/tohin003/AgentGuard/issues. Include:
  - which one you use (AgentGuard Practices or the AgentGuard runtime) and its version
  - your agent product and its version
  - what you expected
  - what happened instead
- **Email.** Write to {{SUPPORT_EMAIL}}.
- **Security problems.** Report them privately, not in public issues. Use GitHub's private vulnerability reporting at https://github.com/tohin003/AgentGuard/security, or email us.

Leave secrets, credentials and other people's personal data out of issues and emails.

We read every report and reply as soon as we can.

## Uninstalling

- **AgentGuard Practices**
  - If you installed it from the plugin directory, remove it on the Plugins page.
  - In the Codex CLI, run `codex plugin remove agentguard-practices@<marketplace>`.
  - In Claude Code, run `claude plugin uninstall agentguard-practices@<marketplace>`.
- **AgentGuard runtime**
  - Remove the AgentGuard plugin from your agent product. For a Claude Code settings install, run `agentguard uninstall`.
  - Then delete `~/.agentguard` to remove its local data.

## Related pages

- [Privacy policy](https://github.com/tohin003/AgentGuard/blob/master/docs/legal/PRIVACY.md)
- [Terms of use](https://github.com/tohin003/AgentGuard/blob/master/docs/legal/TERMS.md)
