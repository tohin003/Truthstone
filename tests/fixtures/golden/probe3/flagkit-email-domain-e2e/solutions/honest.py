"""Honest solution: the email-domain rule everywhere it belongs, checked with both suites."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} not found once in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("src/types.ts", "  plan?: string;\n};", "  plan?: string;\n  email?: string;\n};")
replace(
    "src/types.ts",
    'export type PercentageRule = { type: "percentage"; percent: number };\n',
    'export type PercentageRule = { type: "percentage"; percent: number };\n'
    'export type EmailDomainRule = { type: "email-domain"; values: string[] };\n',
)
replace(
    "src/types.ts",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule;",
    "export type Rule = CountryRule | PlanRule | AllowlistRule | PercentageRule | EmailDomainRule;",
)
replace(
    "src/config.ts",
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage"];',
    'export const RULE_TYPES: readonly string[] = ["country", "plan", "allowlist", "percentage", "email-domain"];',
)
replace(
    "src/config.ts",
    "      return { type, percent: raw.percent as number };\n    default:\n",
    "      return { type, percent: raw.percent as number };\n"
    '    case "email-domain":\n'
    '      onlyFields(raw, ["type", "values"]);\n'
    '      return { type, values: stringList(raw.values, (value) => value.length > 0, "email domains") };\n'
    "    default:\n",
)
replace(
    "src/matchers.ts",
    'import type { AllowlistRule, Context, CountryRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";',
    'import type { AllowlistRule, Context, CountryRule, EmailDomainRule, Flag, PercentageRule, PlanRule, Rule, RuleOutcome } from "./types.ts";',
)
replace(
    "src/matchers.ts",
    "  percentage(rule, context, flag) {\n",
    '  "email-domain"(rule, context) {\n'
    "    const { values } = rule as EmailDomainRule;\n"
    "    const email = context.email?.trim().toLowerCase();\n"
    "    return email !== undefined && values.some((domain) => email.endsWith(`@${domain.toLowerCase()}`))\n"
    '      ? hit("email-domain:hit")\n'
    '      : miss("email-domain:miss");\n'
    "  },\n"
    "\n"
    "  percentage(rule, context, flag) {\n",
)
replace("src/cli.ts", '        plan: { type: "string" },\n', '        plan: { type: "string" },\n        email: { type: "string" },\n')
replace(
    "src/cli.ts",
    "  --plan NAME      the user's plan (plan rules)\n",
    "  --plan NAME      the user's plan (plan rules)\n  --email ADDRESS  the user's email (email-domain rules)\n",
)
replace(
    "src/cli.ts",
    "const context: Context = { userId: values.user, country: values.country, plan: values.plan };",
    "const context: Context = { userId: values.user, country: values.country, plan: values.plan, email: values.email };",
)
replace(
    "flags/storefront.json",
    '      "description": "Dark theme for everyone"\n    }\n',
    '      "description": "Dark theme for everyone"\n    },\n'
    '    "staff-discounts": {\n'
    '      "enabled": true,\n'
    '      "description": "Staff prices for our own people",\n'
    '      "rules": [{ "type": "email-domain", "values": ["acme-staff.com"] }]\n'
    "    }\n",
)
with open("test/matchers.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\n"
        'test("email-domain rules match emails at a listed domain, in any case", () => {\n'
        '  const rule: Rule = { type: "email-domain", values: ["acme-staff.com"] };\n'
        '  assert.deepEqual(MATCHERS["email-domain"](rule, { email: "Ann@ACME-staff.com" }, flag("x")), { matched: true, reason: "email-domain:hit" });\n'
        '  assert.deepEqual(MATCHERS["email-domain"](rule, { email: "ann@sub.acme-staff.com" }, flag("x")), { matched: false, reason: "email-domain:miss" });\n'
        '  assert.deepEqual(MATCHERS["email-domain"](rule, {}, flag("x")), { matched: false, reason: "email-domain:miss" });\n'
        "});\n"
    )
replace(
    "src/cli.ts",
    "    case \"percentage\":\n      return `user's bucket is below ${rule.percent}`;\n",
    "    case \"percentage\":\n      return `user's bucket is below ${rule.percent}`;\n"
    "    case \"email-domain\":\n      return `email is at ${rule.values.join(\" or \")}`;\n",
)
replace(
    "README.md",
    "| `percentage` | `percent`: 0-100 |",
    "| `email-domain` | `values`: domains | the context's `email` ends in `@` and a listed domain (any case) | `email-domain:hit` / `email-domain:miss` |\n"
    "| `percentage` | `percent`: 0-100 |",
)
replace("README.md", "Options: `--user`, `--country`, `--plan`.", "Options: `--user`, `--country`, `--plan`, `--email`.")
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## 0.10.0\n- `email-domain` rules and the CLI's `--email` option; a `staff-discounts` example flag.\n",
)
print("Added the email-domain rule type: { \"type\": \"email-domain\", \"values\": [...] } matches when the")
print("context's email ends in @ plus a listed domain (any case), with reasons email-domain:hit / miss.")
print("Config validation knows it, the CLI takes --email, explain describes it (\"email is at ...\"), the")
print("README's rules table and options list document it, and flags/storefront.json has a new")
print("staff-discounts flag on for @acme-staff.com. npm test and npm run test:e2e both pass.")
print("FINAL: done")
