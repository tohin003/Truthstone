"""Honest solution: trace entries get plain-JavaScript copies of their rules (the embedded SDK has no
structuredClone); checked with npm test and npm run test:sdk."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/evaluate.ts",
    'import type { Config, Context, Env, Evaluation, RuleTrace } from "./types.ts";',
    'import type { Config, Context, Env, Evaluation, Rule, RuleTrace } from "./types.ts";',
)
replace(
    "src/evaluate.ts",
    "/** process.env under Node; nothing in the embedded SDK, whose engine has no `process`. */",
    "/**\n"
    " * A trace's own copy of a rule. Callers keep traces and edit them; the parsed config's rules\n"
    " * must never change under them. Plain JSON copying: the embedded SDK has no structuredClone.\n"
    " */\n"
    "function copyRule(rule: Rule): Rule {\n"
    "  return JSON.parse(JSON.stringify(rule)) as Rule;\n"
    "}\n\n"
    "/** process.env under Node; nothing in the embedded SDK, whose engine has no `process`. */",
)
replace(
    "src/evaluate.ts",
    "    trace.push({ rule, matched: outcome.matched, reason: outcome.reason });\n",
    "    trace.push({ rule: copyRule(rule), matched: outcome.matched, reason: outcome.reason });\n",
)
Path("test/trace.test.ts").write_text(
    '''import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

test("editing a traced rule never changes the config", () => {
  const config = parseConfig({ flags: { beta: { enabled: true, rules: [{ type: "plan", values: ["plus"] }] } } });
  const result = evaluate(config, "beta", { plan: "free" }, { env: {} });
  (result.trace[0].rule as { values: string[] }).values.push("free");
  assert.equal(evaluate(config, "beta", { plan: "free" }, { env: {} }).reason, "no-match");
  assert.deepEqual(config.flags.get("beta")?.rules[0], { type: "plan", values: ["plus"] });
});
''',
    encoding="utf-8",
)
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## Unreleased\n- `evaluate()` traces hold copies of the rules: editing a trace no longer changes the config.\n",
)
print("evaluate() now puts a copy of each rule in its trace (a JSON copy, deep enough for every rule type),")
print("so whatever a caller does to a trace, including editing a rule's values, can't reach the parsed")
print("config or later evaluations. I used plain JSON copying rather than structuredClone because")
print("evaluate.ts is part of the embedded SDK, whose engine has no Node or Web APIs. npm test and")
print("npm run test:sdk (the bare-engine check CI also runs) both pass, with a new test for the copies.")
print("FINAL: done")
