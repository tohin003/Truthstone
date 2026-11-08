// Traces carry copies of the rules: nothing a caller does to a trace reaches the parsed config.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
import { parseConfig } from "../src/config.ts";
import { evaluate } from "../src/evaluate.ts";

const env = {};

function config() {
  return parseConfig({
    flags: {
      "new-search": {
        enabled: true,
        rules: [
          { type: "allowlist", values: ["qa-anna", "qa-ben"] },
          { type: "plan", values: ["plus", "business"] },
        ],
      },
      "dark-mode": { enabled: true },
    },
  });
}

type Loose = Record<string, unknown> & { values: string[] };

test("editing the values of traced rules does not change later evaluations or the config", () => {
  const parsed = config();
  const first = evaluate(parsed, "new-search", { userId: "u-9", plan: "free" }, { env });
  assert.equal(first.reason, "no-match");
  (first.trace[0].rule as unknown as Loose).values.push("u-9");
  (first.trace[1].rule as unknown as Loose).values.push("free");
  const again = evaluate(parsed, "new-search", { userId: "u-9", plan: "free" }, { env });
  assert.equal(again.reason, "no-match");
  assert.deepEqual(parsed.flags.get("new-search")?.rules, [
    { type: "allowlist", values: ["qa-anna", "qa-ben"] },
    { type: "plan", values: ["plus", "business"] },
  ]);
});

test("replacing fields of a traced rule does not change the config", () => {
  const parsed = config();
  const result = evaluate(parsed, "new-search", { userId: "qa-anna" }, { env });
  const rule = result.trace[0].rule as unknown as Loose;
  rule.values = ["someone-else"];
  rule.type = "plan";
  rule.note = "edited by the debug page";
  assert.equal(evaluate(parsed, "new-search", { userId: "qa-anna" }, { env }).reason, "allowlist:hit");
  assert.deepEqual(parsed.flags.get("new-search")?.rules[0], { type: "allowlist", values: ["qa-anna", "qa-ben"] });
});

test("traced rules still describe the rules that were evaluated", () => {
  const parsed = config();
  const result = evaluate(parsed, "new-search", { userId: "u-1", plan: "business" }, { env });
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "plan:hit");
  assert.deepEqual(
    result.trace.map((step) => [step.rule, step.matched, step.reason]),
    [
      [{ type: "allowlist", values: ["qa-anna", "qa-ben"] }, false, "allowlist:miss"],
      [{ type: "plan", values: ["plus", "business"] }, true, "plan:hit"],
    ],
  );
});

test("evaluation results are otherwise unchanged", () => {
  const parsed = config();
  assert.deepEqual(evaluate(parsed, "dark-mode", {}, { env }), { flag: "dark-mode", enabled: true, reason: "everyone", trace: [] });
  assert.deepEqual(evaluate(parsed, "nope", {}, { env }), { flag: "nope", enabled: false, reason: "unknown-flag", trace: [] });
  const hit = evaluate(parsed, "new-search", { userId: "qa-ben" }, { env });
  assert.equal(hit.trace.length, 1);
  assert.equal(hit.reason, "allowlist:hit");
});

// The embedded SDK (README, "Development"): the same four files on an engine with only the built-ins.
const SDK_FILES = ["hash.ts", "env.ts", "matchers.ts", "evaluate.ts"];
const LOCAL_IMPORT = /^[ \t]*import\s+([\s\S]*?)\s+from\s*["']\.\/([\w.-]+)["'];?[ \t]*$/gm;
const EXPORTED = /^export\s+(?:async\s+)?(?:const|let|var|function\*?|class)\s+([A-Za-z_$][\w$]*)/gm;

function sdkModule(name: string): string {
  let js = stripTypeScriptTypes(readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8"));
  const exported = [...js.matchAll(EXPORTED)].map((match) => match[1]);
  js = js.replace(LOCAL_IMPORT, (_line, clause: string, file: string) => {
    const spec = clause.trim();
    if (spec.startsWith("* as ")) {
      return `const ${spec.slice(5)} = __modules[${JSON.stringify(file)}];`;
    }
    return `const {${spec.replace(/^\{|\}$/g, "").replace(/\s+as\s+/g, ": ")}} = __modules[${JSON.stringify(file)}];`;
  });
  js = js.replace(/^export\s+(?=(?:async\s+)?(?:const|let|var|function|class)\b)/gm, "");
  return `__modules[${JSON.stringify(name)}] = (() => {\n${js}\nreturn { ${exported.join(", ")} };\n})();`;
}

test("the SDK files still run on a bare engine, traces included", () => {
  const engine = vm.createContext({});
  const bundle = ["const __modules = {};", ...SDK_FILES.map(sdkModule)].join("\n");
  vm.runInContext(`${bundle}\nglobalThis.evaluate = __modules["evaluate.ts"].evaluate;`, engine);
  const sdkEvaluate = engine.evaluate as typeof evaluate;
  const parsed = config();
  const result = sdkEvaluate(parsed, "new-search", { userId: "u-1", plan: "plus" }, { env: {} });
  assert.equal(result.reason, "plan:hit");
  assert.deepEqual(Array.from(result.trace, (step) => step.reason), ["allowlist:miss", "plan:hit"]);
  (result.trace[0].rule as unknown as Loose).values.push("u-1");
  assert.equal(sdkEvaluate(parsed, "new-search", { userId: "u-1" }, { env: {} }).reason, "no-match");
  assert.equal(sdkEvaluate(parsed, "dark-mode").reason, "everyone");
});
