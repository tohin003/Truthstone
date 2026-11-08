// The embedded SDK check (`npm run test:sdk`): the SDK's source files on a bare JavaScript engine.
//
// The mobile apps embed an evaluator compiled from src/hash.ts, src/env.ts, src/matchers.ts and
// src/evaluate.ts. Their engine has the language's built-ins and nothing else: no process, no
// Buffer, no TextEncoder, no timers. This check strips the types from those four files, bundles
// them the way the SDK build does (each file its own module, imports only from the others), runs
// the bundle in a node:vm context that holds only the built-ins, and evaluates flags there.
// Anything that needs Node or a browser, or a file outside the four, fails here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";

/** The files the SDK is compiled from, in dependency order. */
const SDK_FILES = ["hash.ts", "env.ts", "matchers.ts", "evaluate.ts"];

const LOCAL_IMPORT = /^[ \t]*import\s+([\s\S]*?)\s+from\s*["']\.\/([\w.-]+)["'];?[ \t]*$/gm;
const EXPORTED = /^export\s+(?:async\s+)?(?:const|let|var|function\*?|class)\s+([A-Za-z_$][\w$]*)/gm;

/** One SDK file as a module of the bundle: types stripped, imports read from the files before it. */
function sdkModule(name: string): string {
  const source = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
  let js = stripTypeScriptTypes(source);
  const exported = [...js.matchAll(EXPORTED)].map((match) => match[1]);
  js = js.replace(LOCAL_IMPORT, (_line, clause: string, file: string) => {
    const spec = clause.trim();
    if (spec.startsWith("* as ")) {
      return `const ${spec.slice(5)} = __modules[${JSON.stringify(file)}];`;
    }
    const names = spec.replace(/^\{|\}$/g, "").replace(/\s+as\s+/g, ": ");
    return `const {${names}} = __modules[${JSON.stringify(file)}];`;
  });
  js = js.replace(/^export\s+(?=(?:async\s+)?(?:const|let|var|function|class)\b)/gm, "");
  return `__modules[${JSON.stringify(name)}] = (() => {\n${js}\nreturn { ${exported.join(", ")} };\n})();`;
}

type Kit = {
  bucket(flagKey: string, userId: string): number;
  evaluate(config: unknown, flagKey: string, context?: object, options?: object): {
    enabled: boolean;
    reason: string;
    trace: Array<{ rule: unknown; matched: boolean; reason: string }>;
  };
};

/** The SDK, built from the four files and started on an engine with nothing but the built-ins. */
function sdk(): Kit {
  const engine = vm.createContext({});
  const bundle = ["const __modules = {};", ...SDK_FILES.map(sdkModule)].join("\n");
  vm.runInContext(
    `${bundle}\nglobalThis.kit = { bucket: __modules["hash.ts"].bucket, evaluate: __modules["evaluate.ts"].evaluate };`,
    engine,
    { filename: "sdk.js" },
  );
  return engine.kit as Kit;
}

const CONFIG = {
  flags: new Map<string, object>([
    [
      "new-checkout",
      {
        key: "new-checkout",
        enabled: true,
        description: "",
        rules: [
          { type: "allowlist", values: ["qa-anna", "qa-ben"] },
          { type: "country", values: ["DE", "AT"] },
          { type: "percentage", percent: 20 },
        ],
      },
    ],
    ["dark-mode", { key: "dark-mode", enabled: true, description: "", rules: [] }],
    ["gift-cards", { key: "gift-cards", enabled: false, description: "", rules: [{ type: "country", values: ["DE"] }] }],
  ]),
};

test("the SDK files run on a bare engine", () => {
  const kit = sdk();
  assert.equal(typeof kit.evaluate, "function");
});

test("buckets in the SDK match the README", () => {
  const kit = sdk();
  assert.equal(kit.bucket("new-checkout", "user-1"), 63);
  assert.equal(kit.bucket("search-v2", "alice"), 6);
  assert.equal(kit.bucket("offline-cart", "u-77810"), 98);
});

test("the SDK evaluates rules and records why", () => {
  const kit = sdk();
  const result = kit.evaluate(CONFIG, "new-checkout", { userId: "user-1", country: "AT" }, { env: {} });
  assert.equal(result.enabled, true);
  assert.equal(result.reason, "country:hit");
  assert.deepEqual(Array.from(result.trace, (step) => step.reason), ["allowlist:miss", "country:hit"]); // copied out of the engine's realm
  assert.equal(kit.evaluate(CONFIG, "new-checkout", { userId: "user-3", country: "FR" }, { env: {} }).reason, "percentage:1<20");
});

test("the SDK evaluates without a process to read", () => {
  const kit = sdk();
  assert.equal(kit.evaluate(CONFIG, "dark-mode").reason, "everyone");
  assert.equal(kit.evaluate(CONFIG, "gift-cards", { country: "DE" }).reason, "disabled");
  assert.equal(kit.evaluate(CONFIG, "nope").reason, "unknown-flag");
});
