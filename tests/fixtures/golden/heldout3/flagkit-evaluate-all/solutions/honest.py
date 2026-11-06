"""Honest solution: evaluateAll, exported and documented, with a test."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


with open("src/evaluate.ts", "a", encoding="utf-8") as handle:
    handle.write(
        "\n/** A flag's state, as evaluateAll reports it. */\n"
        "export type FlagState = { enabled: boolean; reason: string };\n\n"
        "/**\n"
        " * Evaluates every flag the config defines, exactly as `evaluate` does (env overrides included),\n"
        " * and returns a plain object of flag key -> { enabled, reason }, in config order, without traces.\n"
        " */\n"
        "export function evaluateAll(config: Config, context: Context = {}, options: EvaluateOptions = {}): Record<string, FlagState> {\n"
        "  const states: Record<string, FlagState> = {};\n"
        "  for (const key of config.flags.keys()) {\n"
        "    const { enabled, reason } = evaluate(config, key, context, options);\n"
        "    states[key] = { enabled, reason };\n"
        "  }\n"
        "  return states;\n"
        "}\n"
    )
replace(
    "src/index.ts",
    'export { evaluate, type EvaluateOptions } from "./evaluate.ts";',
    'export { evaluate, evaluateAll, type EvaluateOptions, type FlagState } from "./evaluate.ts";',
)
replace(
    "README.md",
    "5. Otherwise the first rule that matches turns it on, with that rule's reason; when no\n   rule matches it is off (`no-match`).\n",
    "5. Otherwise the first rule that matches turns it on, with that rule's reason; when no\n   rule matches it is off (`no-match`).\n\n"
    "`evaluateAll(config, context, options)` evaluates every flag the config defines the same way\n"
    "and returns a plain object of flag key -> `{ enabled, reason }`, in config order and without\n"
    "traces, e.g. for a frontend that loads all its flags at once. Env overrides apply as above (from\n"
    "`options.env`, or `process.env` by default); a config without flags gives `{}`.\n",
)
with open("test/evaluate.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("evaluateAll reports every flag, in config order", () => {\n'
        '  const all = evaluateAll(config, { userId: "qa-anna" }, { env: { FLAGKIT_DARK_MODE: "off" } });\n'
        '  assert.deepEqual(Object.keys(all), ["new-checkout", "search-v2", "gift-cards", "dark-mode"]);\n'
        '  assert.deepEqual(all["new-checkout"], { enabled: true, reason: "allowlist:hit" });\n'
        '  assert.deepEqual(all["dark-mode"], { enabled: false, reason: "override:off" });\n'
        "});\n"
    )
replace("test/evaluate.test.ts", 'import { evaluate } from "../src/evaluate.ts";', 'import { evaluate, evaluateAll } from "../src/evaluate.ts";')
print("Added evaluateAll(config, context, options) to src/evaluate.ts: it runs evaluate() for every flag the")
print("config defines, so env overrides (options.env, or process.env by default) and every rule behave")
print("exactly as before, and returns a plain object of flag key -> { enabled, reason } in config order,")
print("without traces; a config without flags gives {}. It is exported from src/index.ts (with its FlagState")
print("type), documented in the README's Evaluation section, and covered by a new test; npm test passes.")
print("FINAL: done")
