# Support

{{PUBLISHER_NAME}} maintains Truthstone Practices, the skills plugin, and Truthstone (previously named AgentGuard), the local runtime.

## Getting help

- **Bugs and questions.** Open an issue at https://github.com/tohin003/Truthstone/issues. Include:
  - which one you use (Truthstone Practices or the Truthstone runtime) and its version
  - your agent product and its version
  - what you expected
  - what happened instead
- **Email.** Write to {{SUPPORT_EMAIL}}.
- **Security problems.** Report them privately, not in public issues. Use GitHub's private vulnerability reporting at https://github.com/tohin003/Truthstone/security, or email us.

Leave secrets, credentials and other people's personal data out of issues and emails.

We read every report and reply as soon as we can.

## Uninstalling

- **Truthstone Practices**
  - If you installed it from the plugin directory, remove it on the Plugins page.
  - In the Codex CLI, run `codex plugin remove truthstone-practices@<marketplace>`.
  - In Claude Code, run `claude plugin uninstall truthstone-practices@<marketplace>`.
- **Truthstone runtime**
  - Remove the Truthstone plugin from your agent product. For a Claude Code settings install, run `truthstone uninstall`.
  - Then delete `~/.truthstone` to remove its local data.

## Related pages

- [Privacy policy](https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md)
- [Terms of use](https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md)
