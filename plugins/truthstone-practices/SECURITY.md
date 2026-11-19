# Security policy

## Scope

This plugin contains only Markdown instructions (skills), YAML display metadata, JSON manifests and image assets. It has no executable code and no hooks. The edition in the ChatGPT and Codex plugin directory also declares one remote MCP server, Truthstone checks (source in `services/truthstone-checks` of the repository), whose tools are read-only and run nothing; a security issue in that server is in scope too.

A security issue in this plugin is an instruction that could lead an agent to cause harm, for example by:

- leaking a secret
- bypassing the platform's approval prompts
- running a destructive command without the user's consent

## Reporting a vulnerability

Report vulnerabilities privately, not in a public issue. Use GitHub's private vulnerability reporting for https://github.com/tohin003/Truthstone: open the **Security** tab and select **Report a vulnerability**. You can also email the publisher, Tohin Majumder, at tohin1400@gmail.com.

Other ways to reach the maintainer are listed at https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md.

## Supported versions

Only the latest release receives fixes. Update to the newest version before you report a problem.
