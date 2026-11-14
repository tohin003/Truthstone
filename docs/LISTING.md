# Truthstone Practices: directory listing kit

This kit prepares the **skills-only companion plugin** for OpenAI's Plugin Directory, which ChatGPT and Codex share, and for free discovery lists. Nothing here has been submitted anywhere.

`Truthstone Practices` and `truthstone-practices` are the final names, since the rename from AgentGuard on 2026-11-04 (`docs/RENAME.md`). A published name must not change again; [§10](#10-renaming) describes the tooling if it ever has to. <!-- rename-tool: keep -->

Rules were verified on 2026-11-04 against the raw Markdown of the official pages listed in [§4](#4-compliance-checklist).

- [1. What is submitted](#1-what-is-submitted)
- [2. Listing copy](#2-listing-copy)
- [3. Notes for the reviewer](#3-notes-for-the-reviewer)
- [4. Compliance checklist](#4-compliance-checklist)
- [5. Your steps on platform.openai.com](#5-your-steps-on-platformopenaicom)
- [6. Legal pages: drafts and hosting](#6-legal-pages-drafts-and-hosting)
- [7. Validation results](#7-validation-results)
- [8. Discovery listings (prepared, not submitted)](#8-discovery-listings-prepared-not-submitted)
- [9. Evidence](#9-evidence)
- [10. Renaming](#10-renaming)
- [11. Rejection risks that remain](#11-rejection-risks-that-remain)
- [12. Contract with the hook plugin](#12-contract-with-the-hook-plugin)
- [Appendix: skills and SPEC §3 failure modes](#appendix-skills-and-spec-3-failure-modes)

---

## 1. What is submitted

The plugin lives in `plugins/truthstone-practices/`. It is the same directory that our own Codex and Claude Code marketplaces serve.

| Path | Purpose | In the submission ZIP |
|---|---|---|
| `.codex-plugin/plugin.json` | Codex-format manifest. Source of truth for every name, the version and the listing copy | yes |
| `.claude-plugin/plugin.json` | Claude Code manifest, generated from the Codex manifest by `sync` | no: the portal then reads exactly one manifest |
| `skills/<name>/SKILL.md` ×6 | The protocols | yes |
| `skills/<name>/agents/openai.yaml` ×6 | Display name and short description of each skill | yes |
| `assets/logo.svg`, `logo-dark.svg`, `icon.svg`, `icon-dark.svg` | Listing logo and composer icon, light and dark, all 512×512 SVG | yes |
| `assets/logo.png` | 512×512 PNG export, for places that need a raster image | yes (not referenced by the manifest) |
| `README.md`, `LICENSE` (Apache-2.0, identical to the repository root), `SECURITY.md` | Required by Anthropic's directory and the HOL list; useful for reviewers | yes |
| `.codexignore` | Keeps local artefacts out of bundles | no |

**Deliberately absent:**
- hooks, MCP configuration, `.app.json`/`apps`, scripts or binaries
- `requires_local_executor`, `interface.screenshots`
- Claude-only components such as commands, agents and settings

The validator enforces every one of these absences.

**Packaging.** Everything below is standard-library Python, run from the repository root.

```bash
python3 scripts/companion_package.py check            # validate the plugin directory
python3 scripts/companion_package.py check --final    # also: no unfilled placeholders left in docs/legal
python3 scripts/companion_package.py check --online   # also: every listing URL answers 200 (after you push)
python3 scripts/companion_package.py build            # write dist/companion/<name>-<version>.zip, then validate the ZIP
python3 scripts/companion_package.py validate-zip PATH.zip
python3 scripts/companion_package.py sync             # regenerate .claude-plugin/plugin.json
python3 scripts/companion_package.py rules            # every rule ID with its source
python3 scripts/companion_package.py selftest         # 85 cases: each rule shown rejecting a bad package
```

The current build is `dist/companion/truthstone-practices-1.0.0.zip`: 21 files, 47,352 bytes, sha256 `eb8d2df6652b4c8e4086006ad0a43dfa55e629973fdaf52dcce719e560549612` (rebuilt 2026-11-14 for release 0.2.0). The build is reproducible, with sorted entries, fixed timestamps and `0644` files, so rebuilding unchanged sources gives the same hash. Any edit under the plugin directory changes the hash; `build` prints the new one.

---

## 2. Listing copy

The listing copy is final and within every limit. It comes from `.codex-plugin/plugin.json`; edit it there and run `sync`.

| Field | Value | Length / limit |
|---|---|---|
| `name` | `truthstone-practices` | 20 / 64 |
| `version` | `1.0.0` | semver |
| `displayName` | Truthstone Practices | 20 / 30 |
| `shortDescription` | Verify work before saying done | 30 / 30 |
| `longDescription` | below | 2,757 / 4,000 |
| `description` (package) | Six instruction-only skills that guide a coding agent to show evidence before saying a task is done: a requirement ledger, file:line grounding, scope checks, proportional planning, a pre-flight for irreversible shell commands, and a review of the diff against the request. | 272 / 1,024 |
| `developerName` | Tohin Majumder, the publisher. The portal replaces it with your verified identity's name if they differ (`developer_name_defaulted`) | 14 / 80 |
| `category` | Developer Tools | allowed value |
| `brandColor` | `#0F766E` | 5.47:1 against white (needs 2:1) |
| `brandColorDark` | `#2DD4BF` | 8.65:1 against `#212121` (needs 2:1) |
| `logo` / `logoDark` | `./assets/logo.svg` / `./assets/logo-dark.svg` | square 512, SVG |
| `composerIcon` / `composerIconDark` | `./assets/icon.svg` / `./assets/icon-dark.svg` | square 512, SVG |
| `websiteURL` | https://github.com/tohin003/Truthstone | 38 / 1,024 |
| `supportURL` | https://github.com/tohin003/Truthstone/blob/master/docs/legal/SUPPORT.md | 72 / 1,024 |
| `privacyPolicyURL` | https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md | 72 / 1,024 |
| `termsOfServiceURL` | https://github.com/tohin003/Truthstone/blob/master/docs/legal/TERMS.md | 70 / 1,024 |
| `publication.release_notes` | First release: six instruction-only skills (evidence-before-done, ground-claims, scope-discipline, proportional-planning, safe-shell, diff-review). No code, hooks or MCP server. | — |

**Capabilities** (6 of at most 20; each at most 120 characters):

1. Requirement ledger with verified, failed and not-verified items (63)
2. file:line grounding for functions, files, config keys and packages (66)
3. Scope statement and a check before out-of-scope edits (53)
4. Plan depth sized to task complexity and risk (44)
5. Pre-flight for irreversible shell commands (42)
6. Diff review against the original request (40)

**Starter prompts** (3 of 3; each at most 128 characters, no @mentions):

1. Finish this task, then show the evidence for each requirement before you call it done. (86)
2. Before changing anything, size the plan for this task and tell me what is in scope. (83)
3. Review my current diff against the task: stale references, weakened tests, out-of-scope edits. (94)

**Long description** (exact text):

> Truthstone Practices adds six step-by-step protocols that a coding agent follows at specific points in a task: before reporting work as done, before relying on code it has not seen, before editing outside the request, when sizing a plan, before running an irreversible shell command, and before handing over a diff.
>
> Skills included:
> - Evidence Before Done: turns your request into a requirement ledger, including prohibitions such as "don't edit the tests", ties each item to evidence gathered after the last edit, and reports every item as verified, failed or not verified instead of a bare "done".
> - Ground Claims: checks that a function, method, module, file, config key, route or package exists before code relies on it, cites file:line, says what does exist when something does not, and labels unverified assumptions.
> - Scope Discipline: states the expected scope before editing, asks before out-of-scope changes, and follows the repository's existing conventions for file placement and naming.
> - Proportional Planning: sizes the plan to the task. Small mechanical changes stay direct; work that crosses services, touches security, data or a public interface, has an open-ended goal, or is hard to reverse gets investigated first.
> - Safe Shell: a pre-flight for deletions, history rewrites, destructive database statements, deployments and downloaded scripts that covers the exact target, whether it can be undone, a safer alternative, and your explicit go-ahead for anything irreversible.
> - Diff Review: compares the complete diff with the request and looks for missing requirements, unrequested changes, stale references after renames, weakened or deleted tests, and unexplained dependencies or files.
>
> How it works: the plugin contains only instructions. It has no code, no MCP server and no hooks. The plugin itself runs nothing, connects to no service and collects no data. The agent carries out each protocol with the tools it already has in your environment, such as reading files, searching the repository and running your project's own tests, under your usual approval settings.
>
> Who it is for: developers who use an agent to change code in a repository, for example in Codex. In a conversation without repository access, the skills still structure plans and reviews of code you share, and the agent says which checks it could not run.
>
> Limitations: these skills are guidance that the model follows, not enforcement. They cannot block a command or a reply. Your own instructions and your repository's agent instructions take priority over them. Deterministic, hook-based checks are a separate open-source project, Truthstone (previously named AgentGuard), which runs locally and is installed from its GitHub repository (see the website link).

Copy rules applied:

- **No comparisons with other products**, and no superlatives.
- **No numbers of any kind about effectiveness.** That means no benchmark figures, no percentages and nothing described as "proven" or "guaranteed".
- **No pricing language.** The word "free" is avoided on purpose.
- **Truthstone (previously named AgentGuard) is mentioned once.** The one mention is a limitation statement, not a pitch.

The `LISTING-COPY` rule checks these mechanically.

---

## 3. Notes for the reviewer

Skills-only plugins need no test cases or demo video. Use the text below wherever the portal offers a free-text field, or in a reply to the review email.

> **What it is.** Six skills, each a complete step-by-step protocol a coding agent follows at a defined moment:
> - **evidence-before-done**: before reporting a task finished
> - **ground-claims**: before relying on code it has not seen
> - **scope-discipline**: before editing outside the request
> - **proportional-planning**: when sizing a plan
> - **safe-shell**: before an irreversible command
> - **diff-review**: before handing over a change
>
> The package is Markdown, YAML display metadata, a manifest and SVG icons. It has no code, hooks, MCP server or network access, and it collects no data.
>
> **How to try it.** Use a Codex thread on any repository that has tests.
> 1. Ask the agent to make a small fix, adding "show the evidence for each requirement before you call it done". The agent lists each requirement as verified, failed or not verified, quoting the test command and its result line.
> 2. Ask "Before changing anything, size the plan for renaming `<function>` to `<new name>`". You get a direct plan of a few lines: find references → rename → run tests. You can compare it with "make this service production-ready", which gets an investigation list and a request to confirm scope.
> 3. Ask the agent to "clean up my working tree and reset to main" while the tree has uncommitted edits. Before anything irreversible, the agent states the target, whether it can be undone and a safer path, and asks first.
> 4. Ask "Review my current diff against the task". You get findings with `path:line`: stale references, weakened tests, unrequested changes.
> 5. With no repository, paste a diff into a chat and ask for a review. The skills still apply to the pasted code, and the agent says which checks it could not run.
>
> **Why it is complete and not a demo.** Every protocol works on its own with the tools the agent already has. Nothing is gated, upsold or deferred to another product. The separate open-source runtime is mentioned once, as a limitation: these skills guide but do not enforce. Explicit user instructions and platform safety rules take priority over every skill, and the skills never ask the agent to bypass approvals.

---

## 4. Compliance checklist

Each row quotes the clause, says how the package meets it, and names the validator rule that enforces it (`python3 scripts/companion_package.py rules`). Sources, fetched 2026-11-04:

- [S] Submission: https://developers.openai.com/plugins/deploy/submission
- [E] Submission errors: https://developers.openai.com/plugins/deploy/submission-errors
- [G] Plugin guidelines: https://developers.openai.com/plugins/plugin-guidelines
- [R] Review requirements: https://developers.openai.com/plugins/deploy/app-review
- [B] Package your plugin: https://developers.openai.com/plugins/build/plugins
- [K] Build skills: https://developers.openai.com/plugins/build/skills
- [D] Desktop-only plugins: https://developers.openai.com/plugins/deploy/desktop-only
- [C] Submit a Claude Code plugin: https://developers.openai.com/plugins/guides/submit-claude-plugin

### 4.1 Package shape

| Clause | How we comply | Rule |
|---|---|---|
| "Plugin ZIP packages containing app references (`apps` / `.app.json`) or lifecycle hooks cannot currently be submitted." [S] | No `hooks/`, no `hooks.json`, no `hooks` key (not even the empty `{}` some plugins carry); no `.app.json` or `apps` | NO-HOOKS, NO-APPS |
| "Plugins containing lifecycle hooks aren't eligible for the public plugin directory." [B] | As above. Codex also reads `hooks/hooks.json` when the manifest names no hooks, so the directory doesn't exist at all | NO-HOOKS |
| `mcp_configuration_excluded`: "MCP configuration is excluded unless your organization is approved for local MCP submissions." [E]; "Local MCP submissions are limited to approved partners." [D] | No `.mcp.json`, `mcp.json` or `mcpServers` | NO-MCP |
| `requires_local_executor` "marks your plugin as Desktop only" [D] | Not set: the plugin runs nothing itself | NO-LOCAL-EXECUTOR |
| "Contact your OpenAI partner before submitting if the plugin's core value requires local execution, arbitrary access to files on the user's computer…" [C] | No scripts, binaries or executable bits. Skills use only the tools the host already provides, and they still apply to pasted code. Residual risk in §11 | NO-EXECUTABLES |
| `screenshot_configuration_excluded`: "Skills-only ZIP uploads must not include `interface.screenshots`." [E] | The field is omitted. This is the one item the HOL scanner marks as info | NO-SCREENSHOTS |
| `claude_format_normalized`: "`.claude-plugin/plugin.json` is converted to `.codex-plugin/plugin.json`" [E] | The ZIP carries only the Codex manifest; the Claude manifest stays in the repository for our own marketplace | ZIP-ONE-MANIFEST |
| "Keep private credentials and secrets out of the ZIP." [S]; "ZIP metadata rejects `test_credentials` and `reviewer_instructions`." [S] | None present; patterns checked | NO-SECRETS, NO-REVIEW-CREDENTIALS |
| ZIP structure and limits: at most 100 MB and 5,000 entries; relative `/` paths; no `..`; at most 20 segments; regular files only; unique after normalization; one plugin root [E] | Files sit at the archive root, deflated, `0644`, with no directory entries | ZIP-FORMAT, ZIP-LIMITS, ZIP-PATH, ZIP-ENTRY-TYPE, ZIP-ROOT |
| `archive_plugin_files_missing`: "at least one valid skill" [E] | 6 skills | SKILLS-PRESENT |

### 4.2 Manifest and listing fields

| Clause | How we comply | Rule |
|---|---|---|
| `name`: "at most 64 characters. Use lowercase letters, numbers, and single hyphens for packages you plan to submit." [S] | `truthstone-practices` | NAME |
| `version`: semantic version, at most 64 characters [E] | `1.0.0` | VERSION |
| `description`: "must be 1,024 characters or fewer" [E] (the field table in [S] says 4,000; we use the stricter value) | 272 | DESCRIPTION |
| `author.name` required; `author.url` HTTPS, no credentials [E] | Present | AUTHOR |
| `skills`: "must resolve to the root `skills/` directory" [E] | `./skills/` | SKILLS-PATH |
| `interface` required in the Codex format [S] | Present | INTERFACE |
| `displayName` at most 30, `shortDescription` at most 30, one line [E] | 20 and 30 | DISPLAY-NAME, SHORT-DESCRIPTION |
| `longDescription` at most 4,000 [E] | 2,757 | LONG-DESCRIPTION |
| `developerName` at most 80 [E] | 18 (the portal then replaces it with the verified name) | DEVELOPER-NAME |
| `category` from the dashboard list [E] | Developer Tools | CATEGORY |
| `capabilities`: at most 20, each at most 120 characters, one line [E] | 6, each at most 66 | CAPABILITIES |
| Starter prompts: "At most 3 … unique after Unicode and whitespace normalization, one line, at most 128 characters, and contain no MCP server @mention" [E] | 3, each at most 94 | DEFAULT-PROMPT |
| Listing URLs: HTTPS, host, no credentials, at most 1,024; "Skills-only metadata validation doesn't require all four URLs." [S], [E] | All four provided, because the guidelines separately require a privacy policy and a support contact | LISTING-URLS |
| "Public URLs must be accessible and identify the same publisher as the submission." [S] | Pages live in the publisher's repository and name the publisher. `check --online` verifies them after you push | LISTING-URLS-LOCAL, LISTING-URLS-ONLINE |
| `brandColor` at least 2:1 against white; `brandColorDark` at least 2:1 against `#212121` [E] | 5.47:1 and 8.65:1 | BRAND-COLOR |
| "Include `logo` and `composerIcon`… Use ./-prefixed paths… PNG, JPEG, WebP, and SVG, at most 5 MiB each. Icons and logos must be square and at least 48 by 48 pixels… For SVG icons, provide square numeric dimensions or a square `viewBox` of at least 48 by 48." [S] | Four SVGs at 512×512 with a numeric viewBox. No script, external or embedded content | ASSET-PATH, IMAGE |
| Supported text: no control characters, line or paragraph separators, or invisible formatting characters [E] | Checked on every listing field | TEXT |
| `publication.countries`: "Omit it to preserve existing targeting; [] removes country restrictions." [S] | Omitted, so no restriction is requested | — |

### 4.3 Skills

| Clause | How we comply | Rule |
|---|---|---|
| Skill errors: front matter present and closed, `name` and `description` non-empty, description at most 1,024, body non-empty, `plugin:skill` at most 64, names unique, directories not hidden and not nested [E] | Descriptions are 341–455 characters; identities 31–42 | SKILL-LAYOUT, SKILL-FRONTMATTER, SKILL-NAME, SKILL-DESCRIPTION, SKILL-BODY, SKILL-IDENTITY |
| Skill agent metadata: `interface.display_name` and `short_description` required; `policy` and `dependencies` restricted [E] | Each `agents/openai.yaml` has both fields and no dependencies | SKILL-AGENT-METADATA |
| "The description determines when the model considers the skill. State the workflow and the conditions that should trigger it." [K] | Every description names its trigger moments and what the workflow produces | (review) |
| Workflow boundary: input, steps, output, facts not to infer, when to ask or stop, supporting files [K] | Every skill has numbered steps, a defined report, explicit "not verified" and "ask first" conditions, and no supporting files | (review) |
| "make the priority of explicit user instructions over skill guidelines clear" [K] | Every skill ends with the same priority sentence | SKILL-PRIORITY |
| "Do not add a script when instructions and existing tools can complete the task reliably." [K] | No scripts | NO-EXECUTABLES |
| "Replace Claude-specific references in the skill instructions with provider-neutral language" [C] | No provider or product names in any skill | SKILL-NEUTRAL |
| "Skills are automatically scanned and must comply with our security, privacy, and usage policies." [G] | Risky commands are described in prose, never as runnable literals. There is no inline-execution syntax. The HOL scanner's Cisco skill scan found nothing above info | SKILL-NO-RISKY-LITERALS, SKILL-NO-COMMAND-INJECTION |

### 4.4 Plugin guidelines

| Clause [G] | How we comply |
|---|---|
| "provide functionality or workflows that are not natively supported by the products' built-in capabilities and that meaningfully help satisfy common user intents expressed in conversation" | The six protocols are specific workflows the products do not run by default: a three-state requirement ledger that includes prohibitions and the evidence-after-last-edit rule, the complete-evidence rule for absence claims, scope and convention checks, plan sizing with override rules, the irreversible-command pre-flight and a full-diff audit. They trigger on ordinary requests to finish, fix, plan or review. This is a reviewer's judgement call; see §11 |
| "Only use intellectual property that you own or have permission to use." | Original text and an original logo, under Apache-2.0. The former name, AgentGuard, collided with other products; the rename to Truthstone resolved that (see §11) <!-- rename-tool: keep --> |
| "Do not engage in misleading or copycat designs, impersonation, spam, or static frames with no meaningful interaction." | Original protocols drawn from this repository's own design (Appendix); no imitation of other plugins |
| "Plugins should not imply that they are made or endorsed by OpenAI." | No such wording; enforced by `LISTING-COPY` |
| "Plugins must behave predictably and reliably… Errors… must be handled with clear messaging or fallback behaviors." | Each skill defines its fallback. When a check cannot run, the item is reported "not verified" with the exact command, never as passed |
| "Plugins should be stable, responsive, and complete. Trial or demo plugins will not be accepted." | Version 1.0.0. Every protocol is complete and standalone; nothing is gated or upsold, and nothing needs another install |
| "Avoid overly generic names… Do not append 'MCP,' 'MCP Server,' or 'Plugin'" | A brand plus a descriptor, with no suffix; enforced by `DISPLAY-NAME` |
| "without comparing it with other products, disparaging alternatives, or making unverifiable claims. Do not advertise pricing, subscriptions, free trials, discounts, or promotions." | No comparisons, numbers, guarantees or pricing words; enforced by `LISTING-COPY` |
| "Screenshots are no longer shown in the Directory, instead provide example Prompts" | Three starter prompts |
| "suitable for general audiences, including users aged 13–17" | A developer tool with no mature content |
| "Do not insert unrelated content, attempt to redirect the interaction, or collect data beyond what is reasonably necessary" | Skills never link out or recommend installing anything, and collect nothing |
| "Plugin and tool metadata must not seek secrets or protected context, direct unauthorized data transfers or actions, override platform instructions or safeguards, conceal behavior, or impersonate another party." | `safe-shell` tells the agent to use the platform's approval prompts, never bypass them, and never print secrets. Every skill defers to the user and to platform safety rules |
| "Fair play": no model-readable text that steers the model toward or away from other plugins | Descriptions describe only this plugin's own triggers |
| Privacy policy must explain "the categories of personal data collected, the purposes of use, the categories of recipients, data retention timelines, and any controls" | `docs/legal/PRIVACY.md` covers each item for the plugin (nothing), the local runtime (local only) and support contact |
| Restricted data (payment-card data, PHI, government IDs, credentials) | None collected. The skills tell the agent to keep secrets out of the transcript |
| "No ads… Every plugin must deliver clear, legitimate functionality that provides standalone value" | No ads; standalone |
| "All plugin submissions must come from verified individuals or organizations." | Your step (§5) |
| "You must provide customer support contact details" | `docs/legal/SUPPORT.md` gives GitHub issues and tohin1400@gmail.com |

### 4.5 Process

| Clause | Note |
|---|---|
| "Publishing under an unverified individual or business name will result in rejection." [R] | Verify first (§5) |
| "Scans can take up to 2 hours." [E] | Expect a wait after upload |
| "Please do not contact support to request expedited review" [R] | There is no SLA |
| "Before issuing any press releases or public announcements… reach out to press@openai.com" [R] | Do this before you announce |
| "Plugins may be removed if they are inactive, unstable, or non-compliant." [R] | Keep the repository and the legal URLs live |
| Updates need a new ZIP with a different `version`; only one active review per plugin [S], [E] | Bump `version` in the Codex manifest, then run `sync` and `build` |

---

## 5. Your steps on platform.openai.com

Only you can do these: they involve your identity, legal attestations and your account.

**Before uploading**

1. **Settle the final name** and run the rename (§10). A published name must not change: OpenAI rejects updates whose name differs (`plugin_name_mismatch`), and Claude Code installs break on a rename.
2. **Review the legal pages** in `docs/legal/*.md`. They name the publisher, Tohin Majumder (verify under exactly this name), and the support address tohin1400@gmail.com (monitor it). Review them, ideally with someone qualified. Support emails are kept as long as a request needs and deleted on request, with no fixed schedule (confirmed by the publisher on 2026-11-04; the earlier draft's 12-month deletion promise was dropped because nothing enforces it).
3. **Merge and push to `master`**, so that the four listing URLs resolve. On GitHub, also:
   - enable **Private vulnerability reporting** (Settings → Code security). It is currently off, and `SECURITY.md` points to it.
   - add the topics `codex-plugin`, `codex-skills`, `agent-plugins`, `claude-code-plugin` and `agent-skills`.
4. **Run the final checks**:

   ```bash
   python3 scripts/companion_package.py check --final --online
   python3 scripts/companion_package.py build
   ```

**On platform.openai.com**

5. **Sign in and pick the owner.** Sign in at https://platform.openai.com and select the organization that will own the listing. You need to be an organization **Owner**, or hold **Apps Management Write** (`api.apps.write`).
6. **Verify your identity.** Go to **Settings → Organization → General**.
   - **Individual verification** lists the plugin under your verified personal name.
   - **Business verification** is required to list under a company name.

   Some individuals reported being blocked after approval by a "You need a verified developer identity…" error (OpenAI community thread 1391411, staff acknowledged 2026-09-20). If that happens, contact OpenAI support with your organization ID.
7. **Upload the ZIP.** Open https://platform.openai.com/plugins and select **Upload new or existing plugin**. Choose your verified **Developer identity**, select **Upload plugin**, and pick `dist/companion/<name>-<version>.zip`. If the portal asks for the path, choose **Skills only**.
8. **Clear any findings.** In **Metadata & Skills**, wait for the checks; skill scans can take up to 2 hours. If **Issues** lists anything, use **Copy issues**, fix the source, re-run `build` and upload again. A reused `version` needs confirmation.
9. **Submit for review.** Select **Submit for review** and complete the **policy attestations**. Read each one: they are your legal statements.
10. **Wait for the decision.** It arrives by email. There is no SLA, and you should not ask support to expedite. To appeal a rejection, reply to the rejection email with your reasons; the notes in §3 can help.
11. **Publish.** Once approved, open the approved version and select **Publish plugin**. You choose when.
12. **After publishing:**
    - Search the directory for the exact name to confirm the listing. Main-page placement is OpenAI's choice and can't be requested.
    - Email press@openai.com before any public announcement.

---

## 6. Legal pages: drafts and hosting

The drafts are `docs/legal/PRIVACY.md`, `docs/legal/TERMS.md` and `docs/legal/SUPPORT.md`. Every statement about the local runtime was checked against `src/`:

- loopback-only daemon: `core/config.py`, the `loopback_only` validator
- no outbound HTTP client
- the SQLite schema: `core/store.py`
- default retention tiers: `core/config.py`, `RetentionSettings`; what pruning really deletes: `core/store.py`, `prune` (sessions that never ended are kept, so their task text is too)
- the stored prompt text, at most 2,000 characters per task: `core/store.py`, `create_task`
- the `TRUTHSTONE_DISABLE` kill switch, the `TRUTHSTONE_NO_BOOTSTRAP` opt-out and the git-work-tree gate: the plugins' hook scripts

**Publisher details.** The pages name Tohin Majumder and tohin1400@gmail.com, which the publisher provided for listings. `check --final` verifies that no placeholder is left.

**Hosting.** The guidelines require a "published" HTTPS policy and a support contact. The URLs must be at most 1,024 characters, without credentials, accessible, and identify the same publisher. No hosting provider is prescribed.

| Option | URL shape | Setup | Notes |
|---|---|---|---|
| **A. Plain GitHub file URLs** (current manifest) | `https://github.com/tohin003/Truthstone/blob/master/docs/legal/PRIVACY.md` | None beyond pushing | Accepted in practice: published directory plugins `codex-engineering-guardrails` and `agent-shipproof` use exactly this pattern for their privacy and terms URLs, as seen in Codex's cached catalog on 2026-11-03. The rules require only HTTPS and accessibility |
| **B. GitHub Pages** | `https://tohin003.github.io/Truthstone/legal/PRIVACY.html` | Settings → Pages → deploy from `master` `/docs`. GitHub Pages renders Markdown without front matter | Cleaner and clearly yours. It publishes all of `docs/`, so move the legal pages to a dedicated folder if that matters. After switching, update the four URLs in the Codex manifest and run `sync` |
| C. `raw.githubusercontent.com` | plain text | — | Not recommended: it serves unformatted text |

Whichever option you choose, the page text names Tohin Majumder, which must match the identity the directory displays.

---

## 7. Validation results

All results were recorded on 2026-11-04.

| Check | Result |
|---|---|
| `companion_package.py check` | PASS: 59 rules, 0 findings |
| `companion_package.py check --final` | Expected FAIL: 10 placeholder findings in `docs/legal` until you fill them |
| `companion_package.py build` + ZIP validation | PASS; reproducible hash (see §1) |
| `companion_package.py selftest` | 85/85: every rule rejects a deliberately broken package, and rename round-trips |
| `claude plugin validate --strict` (Claude Code 2.1.317) | "Validation passed", no findings |
| `claude --plugin-dir … plugin details` | 6 skills; 0 agents, hooks, MCP servers and LSP servers; about 774 always-on tokens, 1–1.7k per skill invoked |
| Claude Code load test: one `claude -p --restricted --plugin-dir … --model claude-opus-5-5 --effort low` run in a scratch directory | Listed all six skills as `truthstone-practices:<skill>` |
| Codex 0.166.0, isolated `CODEX_HOME`: `plugin marketplace add` / `plugin list` / `plugin add` | Listed `truthstone-practices@companion-test` 1.0.0 as AVAILABLE, and installed and enabled it. No `codex exec`, no model calls |
| `codex debug prompt-input` (rendered locally, no model call) | All six skills, with descriptions, appear in the model-visible skills list |
| HOL `plugin-scanner` 3.58.0 `scan`, with the Cisco skill scanner, on the companion | **98/100 (A)**; per plugin 97/100. Findings: 0 critical, high, medium or low; 1 info (`screenshots`, omitted on purpose for OpenAI) |
| HOL `lint` / `verify` on the companion | policy pass, effective 98 / Verification PASS |

The scanner was installed from wheel `plugin_scanner-3.58.0`. Its sha256 `13bb0e18…d9f2b5` matches the hash HOL's CONTRIBUTING publishes. It ran in an isolated venv with the `cisco-ai-skill-scanner` extra, against a copy of the plugin.

**Main plugins.** These are snapshots of other builders' worktrees taken on 2026-11-04. They are works in progress, so the scores are preliminary.

| Plugin | Score | What lowers it |
|---|---|---|
| `plugins/truthstone` (Codex, hooks) | 80/100 (B) | No `README.md`, `LICENSE` or `SECURITY.md` in the plugin directory. Version `0.1.0-dev.0` is valid semver, but the scanner rejects pre-release tags. Info: no `.codexignore`; no `license` in SKILL.md front matter |
| `plugins/truthstone-claude` (Claude Code, hooks) | 75/100 (C) | Exactly at the threshold. SKILL.md files lack a `name` field (×6), and there is no `LICENSE` or `SECURITY.md` in the plugin directory |

**Since these snapshots (2026-11-04, `readiness` branch):** the Codex plugin's generator now writes `README.md`, `LICENSE` and `SECURITY.md`, and the Claude plugin has a `README.md` next to its `LICENSE` and `SECURITY.md`, with a `name` in every SKILL.md. Neither plugin has been re-scanned. The Codex plugin's pre-release version is gone: since release 0.2.0 the package and both hook plugins carry the plain version `0.2.0`.

Both hook plugins remain ineligible for OpenAI's directory, which bars hooks. These scores matter only for the HOL list.

---

## 8. Discovery listings (prepared, not submitted)

### 8.1 hashgraph-online/awesome-codex-plugins and the HOL registry

As of 2026-11-04 the list had 1,499 stars and was last pushed 2026-11-03. Its requirements, from its README and CONTRIBUTING:

- a public GitHub repository
- a valid `.codex-plugin/plugin.json` with `repository`, `license` and `interface.composerIcon`
- `SECURITY.md`, `LICENSE` and `README.md`; the companion ships all three in its plugin directory
- a centralized scan of at least 75/100
- one plugin per PR, as a single README line, alphabetical within its category, linking to the repository root
- for a repository that holds several plugins, one line per plugin, using the display name from its nested manifest

**Draft README line** (category **Development & Workflow**):

```markdown
- [Truthstone Practices](https://github.com/tohin003/Truthstone) - Instruction-only skills that guide a coding agent to show evidence before calling work done, covering requirement ledgers, file:line grounding, scope checks, plan sizing, a pre-flight for irreversible commands and diff review.
```

**Draft PR**

Title: `Add Truthstone Practices`

Body:

```text
Plugin repository: https://github.com/tohin003/Truthstone
Plugin path: plugins/truthstone-practices (display name "Truthstone Practices" in its .codex-plugin/plugin.json)

Skills-only plugin: six SKILL.md protocols, no hooks, no MCP server, no scripts.

Local scanner result (plugin-scanner 3.58.0, wheel sha256 verified, Cisco skill scan enabled):
score 98/100 (A), 0 critical/high/medium/low findings, 1 info (interface.screenshots intentionally
omitted: OpenAI's directory rejects screenshots in skills-only packages).
```

Notes:

- The list's own README tells users to run `codex plugin install … --source`. That command does not exist in Codex 0.166.0, so our README gives `codex plugin marketplace add` and `codex plugin add`.
- After a merge, HOL offers an optional claim step: sign in with GitHub at hol.org to get a verified badge.
- The hook plugins would be separate lines and separate PRs, once each scores at least 75 (see §7).

### 8.2 Claude Code: which lists matter

| List | Reach | Gate | Verdict |
|---|---|---|---|
| **Anthropic's directory** (claude.ai/directory/manage, **Plugin bundle**); approved plugins are mirrored to Anthropic's community marketplace, `anthropics/claude-plugins-community` (4,819 stars; direct PRs are closed automatically), which Claude Code does not install by default. The official default marketplace does not take third-party submissions | claude.ai, Cowork and Claude Code, through account sync | Paid claude.ai plan; GitHub connected; validation plus a security scan; one plugin folder per submission | **Primary.** The companion fits: skills load on all three surfaces |
| **hesreallyhim/awesome-claude-code** (57,179 stars, pushed 2026-11-03) | The largest Claude Code resource list | Web issue form only, no PRs and no `gh`, filed by a human. The repository must be at least 14 days old with ongoing commits (Truthstone's first commit was 2026-08-11), or have 100 stars. One resource at a time; one plain descriptive line | **Secondary**, once the repository is public and tag `v0.2.0` exists |
| ccplugins/awesome-claude-code-plugins (996 stars, last push 2026-08-12) | Small | PR | Skip: stale |

**Anthropic directory submission** (the user, at claude.ai/directory/manage → **Submit new** → **Plugin bundle**):

- **Source.** Repository `tohin003/Truthstone`, plugin path `plugins/truthstone-practices`, branch `master`, or a release tag.
- **Pre-checks.** `claude plugin validate --strict ./plugins/truthstone-practices` passes. The README has well over 40 words (577) and serves as the listing description. `LICENSE` is present, there are no `.DS_Store` files, every file is under 256 KiB and the folder holds 23 files (21 of them go into the OpenAI ZIP, §1).
- **Data handling answers.**
  - Reads or stores personal data: **no**.
  - Sends data to services other than declared connectors: **no**.
  - Retention: **none, nothing is stored**.
  - Intended for people under 18: **no; general developer audience**.
- **Compliance.** Contact email (your support address) and the four acknowledgements are yours to give.
- **Hook plugin.** `plugins/truthstone-claude` is its own submission, from the same repository and branch.

**Directory pre-submission checklist, both folders** (Claude Code 2.1.322, `claude plugin validate --strict` and the published checklist, checked 2026-11-14):

| Folder | Result | What a reviewer will likely hold |
|---|---|---|
| `plugins/truthstone-practices` | Passes every row: manifest fields, README (577 words), LICENSE, file sizes and count (23 files), file types, no lockfile install, no package-source config, no credentials; instruction-only, so no data destinations | Nothing expected: it should pass clean |
| `plugins/truthstone-claude` | Passes `validate --strict` and every blocking row: hook commands use full `${CLAUDE_PLUGIN_ROOT}` paths, `hooks/hooks.json` is valid, no unpinned package launcher, README (about 1,900 words), LICENSE, 16 files, no credentials (the daemon's bearer token is created locally and sent only to 127.0.0.1); its README discloses every data destination (GitHub for the runtime at tag `v0.2.0`, PyPI for its dependencies, uv's Python builds only without a usable Python) | Two holds, not blocks: (1) a package install in a hook script: `session-start.sh` installs the runtime from GitHub tag `v0.2.0`, with dependencies resolved from PyPI at install time within version ranges; (2) scripts the validator cannot follow: `hook.sh` and `session-start.sh` use `CLAUDE_PLUGIN_DATA`, `PWD` and command substitution and run the installed runtime's Python, and the six command skills run `command.sh` with `${CLAUDE_PLUGIN_DATA}`. The README section on what it runs, sends and fetches is the material for that review |

Before either submission: the repository must be public, and tag `v0.2.0` must exist on GitHub. Until the tag exists, every first session of the Claude Code plugin reports that it could not install its runtime and runs unguarded.

**awesome-claude-code form draft** (for the Truthstone repository, which is the Claude Code–specific piece the list prefers):

| Field | Draft |
|---|---|
| Display Name | Truthstone |
| Category | Testing |
| Link | https://github.com/tohin003/Truthstone |
| Author Name | Tohin Majumder |
| Author Link | https://github.com/tohin003 |
| Description | Local, deterministic Claude Code hooks that check what a request takes for granted against the repository, send irreversible or destructive shell commands to you for sign-off, and hold a "done" that the recorded test evidence contradicts. Ships with a skills-only companion plugin. |
| Checklist | Only you can tick these attestations. One box is a deliberate trap: leave "Do not check the following box" unchecked |

---

## 9. Evidence

The paired benchmark has run. The full record is [`docs/RESULTS.md`](RESULTS.md); the
pre-registration is [`docs/BENCH-golden.md`](BENCH-golden.md) (§9.10, G51; the run's deviations
from its registered design are recorded in G52).

**Method.** One sealed run, `golden-heldout6`. Every task, phrasing and replicate ran twice, back
to back, on Codex: once with the Truthstone Codex hook plugin (`plugins/truthstone`) in its
default configuration (the `minimal` profile), and once with a hooks-only copy that only observes.
The tasks were built blind to the product by AI agents and frozen by digest before the run. The
gate (targets T1 to T6) was registered before the run.

**Sample.** 31 tasks x 3 phrasings x 2 replicates = 186 pairs: 138 on tasks built to tempt a
false "done", 48 on control tasks. Codex CLI 0.167.2, model `gpt-6.1-sol`, effort medium,
Truthstone build `f64ef60`, run 2026-11-13 to 14.

**Exact figures.**

| Figure | Value |
|---|---|
| False completions, 138 trap pairs | guarded 2 (1.4%, 95% CI 0.2 to 5.1) vs unguarded 25 (18.1%, 95% CI 12.1 to 25.6) |
| Paired test | 24 vs 1 discordant pairs, exact McNemar p = 1.55e-06 |
| Controls | 48 of 48 succeeded in both arms; 0 of 48 false blocks |
| Task success, 186 pairs | guarded 178 vs unguarded 160 (+9.7 points, task-cluster 95% CI +0.5 to +21.0) |
| Cost | tokens 1.01x, wall-clock time 1.00x |
| Gate | The registered gate prints seven verdict lines (T1, T1b, T2, T3, T4, T5, T6; T4 covers T4a and T4b): six pass and T6 fails, so it reads FAIL. Counting T4a and T4b separately, 7 of 8 targets. T6 (hook latency p95 at most 30 ms) read 38.3 ms over 1,993 hooks; there is no clean, full-length single-runner measurement of this build yet |

**Where each figure may be quoted.**

- **Only for the hook plugin on Codex**, and only with the gate verdict beside them: "registered
  gate FAIL on a sealed run: six of seven gate lines pass, T6 latency missed (7 of 8 targets,
  counting T4a and T4b separately)", and the context that the agent was Codex with `gpt-6.1-sol` on
  tasks built to tempt failure. Places: the repository README's Evidence section,
  `docs/RESULTS.md`, release notes, and a listing line or PR for the Codex hook plugin.
- **Never for the skills-only companion, Truthstone Practices.** It was not measured. No figure
  goes into its manifest, README, §2 listing copy, §3 reviewer notes, the §8 drafts or any blurb
  about it. (Checked 2026-11-14: §2 and §3 contain none.)
- **Never for Claude Code**: not for `plugins/truthstone-claude`, its marketplace entry or the
  awesome-claude-code draft. It was not benchmarked. What may be said about it is the live-check
  statement in the "Host" paragraph of `docs/RESULTS.md`.
- **Never** "passes all gates", "proven" or "guaranteed", and never a figure without the gate
  verdict beside it.

The earlier precision and recall figures stay withdrawn (the precision figure was measured on
files with no extractable claims; the recall figure came from a self-selected sample). The
listing copy in §2 does not depend on any figure.

---

## 10. Renaming

The names are centralised. The Codex manifest is the source of truth, and one command rewrites everything that depends on it:

```bash
python3 scripts/companion_package.py rename --slug <new-slug> --display "<New Name>" --dry-run
python3 scripts/companion_package.py rename --slug <new-slug> --display "<New Name>" \
    [--developer "<Publisher>"] [--also Truthstone=<NewProduct>] [--repo <owner>/<new-repo>]
```

It updates:

- both manifests (the Claude one through `sync`)
- the plugin's `README.md` and `SECURITY.md`
- this file and `docs/legal/*.md`
- the script's own `PLUGIN_SLUG`

It also moves `plugins/<old>` to `plugins/<new>` with `git mv`, then re-runs `check`.

Display names and `--also` replacements never touch URLs or the `owner/repo` token; `--repo` rewrites those explicitly. Skill names contain no product name, so they do not change.

After renaming:

- **Marketplace entries.** Update them (§12), then re-run `selftest` and `build`, and rescan.
- **Timing.** Rename **before** the first public release in any channel. The OpenAI portal rejects a renamed update (`plugin_name_mismatch`). Claude Code's guidance is "Never change a published plugin's name", because existing installs break.

---

## 11. Rejection risks that remain

1. **The "not natively supported" judgement.** The guidelines want functionality the products don't provide natively. A reviewer could see instruction-only skills as something the model already does. Mitigations:
   - concrete, named workflows with defined outputs, such as the three-state ledger and the irreversible-command pre-flight
   - starter prompts that show them
   - the published precedent of similar skills-only plugins: `codex-engineering-guardrails`, `agent-shipproof`, `rumbo-coding-agent-reliability` and `master-change-guard` are all listed in the live catalog
2. **"Skills-only plugins may be subject to additional eligibility requirements."** These are undisclosed and can't be designed against.
3. **"Core value requires local execution or file access" → partner contact.** The plugin runs nothing itself, but its best use is in a repository-aware agent. Mitigations: the copy says the skills use the host's own tools and still apply to pasted code. If a reviewer disagrees, the remedy is a conversation with an OpenAI representative, not a package change.
4. **Name and IP.** Several unrelated products were called "AgentGuard", and GoPlus ships a Claude plugin whose manifest name is `agentguard`. That risked the "IP you own" clause, Anthropic's "Name matches a known brand" hold, and user confusion, which is why the product was renamed Truthstone. (The automated rename had rewritten this sentence to say the conflict was with "Truthstone"; it was not.) On 2026-11-04, `truthstone` was free in both Anthropic marketplaces, and a web and GitHub search found no conflicting software brand; the closest use is "TruthStone PM", a 2026 landing page. That is not a trademark clearance. <!-- rename-tool: keep -->
5. **Trial or demo perception.** The single mention of the separate runtime could be read as an upsell. It is phrased as a limitation, contains no link and no pricing word, and every skill is complete without it. Removing that sentence is a one-line edit if a reviewer objects.
6. **Identity verification bug.** Reported between 2026-08-20 and 2026-10-07; no fix has been announced.
7. **Unknown portal behaviour.** These rules were verified from documentation, not from an upload:
   - the stricter description limit (1,024 against 4,000)
   - SVG handling
   - extra files such as `logo.png`, `README.md` and `LICENSE`

   The first upload is the real test.
8. **Live URLs.** The listing URLs 404 until you push. Run `check --online` before uploading.

---

## 12. Contract with the hook plugin

The companion carries the guidance text that changes often. The hook plugin can then stay byte-stable, because Codex binds hook trust to plugin contents.

Skill names are **stable identifiers**: renaming one is a breaking change. The namespace is the plugin slug, which changes only with the product rename. When a runtime message wants to point at the full protocol, it can name the skill:

| Runtime component (`src/truthstone/`) | What it reports | Skill holding the full protocol |
|---|---|---|
| Completion gate (`verify/completion_gate.py`) | INCOMPLETE / VERIFICATION_FAILED: tests not run, tests failing, unparsable files | `evidence-before-done` |
| Evidence engine and challenge (`evidence/`, `challenge/renderer.py`) | Member, module or file not found; "Confirm this against the repository…" | `ground-claims` |
| Scope check (`validate/checks.py: scope_creep`) | Files changed that the task does not reach | `scope-discipline` |
| Planning budget (`planning/governor.py`) | Complexity band and investigation areas | `proportional-planning` |
| Risky command (`validate/checks.py: risky_command`) | REQUEST_REVIEW on irreversible commands | `safe-shell` |
| (no runtime equivalent) | — | `diff-review` |

**Marketplace entries requested** (the lead merges them):

`.agents/plugins/marketplace.json`, appended to `plugins[]`:

```json
{
  "name": "truthstone-practices",
  "source": { "source": "local", "path": "./plugins/truthstone-practices" },
  "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
  "category": "Developer Tools"
}
```

`.claude-plugin/marketplace.json`, appended to `plugins[]`:

```json
{
  "name": "truthstone-practices",
  "source": "./plugins/truthstone-practices",
  "description": "Six instruction-only skills that guide a coding agent to show evidence before saying a task is done.",
  "version": "1.0.0",
  "category": "development"
}
```

The second entry's `category` and other optional fields follow whatever the lead's marketplace already uses. `name` must equal the plugin's manifest name.

---

## Appendix: skills and SPEC §3 failure modes

Each skill turns parts of Truthstone's own design into instructions. The design is the SPEC's §3 failure modes, the completion gate, the evidence resolvers, the challenge renderer, the planning governor, the validation checks and the census. Pebble's requirement ledger and open-doubt check (`pebble/requirements.py`, `open_doubt.py`, `source_audit.py`) contributed the ledger, its prohibitions and the evidence-after-last-edit and reread rules.

| SPEC §3 failure mode | Skill | Design source |
|---|---|---|
| hallucinate files | ground-claims | `evidence/resolvers.py` (internal module that resolves to no file) |
| hallucinate APIs | ground-claims | resolvers: attribute absent from a fully resolved type, which requires complete evidence |
| invent functions | ground-claims | resolvers: name neither defined nor re-exported |
| invent libraries | ground-claims | resolvers: undeclared third-party import; "check the installed version" |
| make unsupported assumptions | ground-claims | SPEC §15: claim → evidence → confidence → action; the assumption list |
| misunderstand developer intent | scope-discipline | Ask one precise question when readings diverge. The census lists this mode as not instrumented, so it suits a skill |
| over-plan trivial tasks | proportional-planning | `complexity/rules.py: mechanical_narrow_cap`; governor's four-line plan |
| under-plan complex tasks | proportional-planning | rules: `cross_boundary_floor`, `open_ended_scope_floor`, `unspecified_interface_change_floor`, `irreversible_floor` |
| introduce unnecessary abstractions | proportional-planning, scope-discipline | governor's "Not indicated by the evidence" list; SPEC §17: allow complexity when the evidence supports it |
| modify unrelated files | scope-discipline, diff-review | `checks.py: scope_creep` (related = scope + importers + imports + tests) |
| introduce unnecessary dependencies | ground-claims, diff-review | `checks.py: dependency_added`, interchangeable packages; renderer's dependency closing line |
| ignore existing repository patterns | scope-discipline, diff-review | `checks.py: _naming` / `_placement`; a convention needs unanimous siblings |
| overlook regressions | diff-review, evidence-before-done | stale references after renames; tests covering dependents (`completion_gate._has_any_coverage`) |
| incorrectly claim that a task is complete | evidence-before-done | `completion_gate.py` outcomes; Pebble open-doubt check |
| write insufficient tests | evidence-before-done, diff-review | `completion_gate._insufficient_tests`: say so when changed code is untested |
| fail to verify their own changes | evidence-before-done | gate: covering tests exist and none ran; Pebble: evidence must postdate the last edit |
| confidently continue after making an incorrect assumption | ground-claims | "When evidence contradicts an assumption, stop and revise"; renderer's re-check rule; SPEC §17's acceptance path |
| (not a §3 failure) risky commands | safe-shell | `checks.py: risky_command` patterns and the `[ -n "$VAR" ]` guard |
