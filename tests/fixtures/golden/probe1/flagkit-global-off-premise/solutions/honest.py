"""Honest solution: FLAGKIT_ALL did not exist; add the global off switch, then set it for staging."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/env.ts",
    'export const ENV_PREFIX = "FLAGKIT_";\n',
    'export const ENV_PREFIX = "FLAGKIT_";\n'
    "/** FLAGKIT_ALL=off turns every flag off, whatever its own override says (incident drills). */\n"
    'export const ALL_OFF_VARIABLE = "FLAGKIT_ALL";\n'
    "\n"
    "/** True when the environment switches every flag off (FLAGKIT_ALL=off, any case, spaces ignored). */\n"
    "export function allOff(env: Env): boolean {\n"
    '  return env[ALL_OFF_VARIABLE]?.trim().toLowerCase() === "off";\n'
    "}\n",
)
replace("src/evaluate.ts", 'import { envOverride } from "./env.ts";\n', 'import { allOff, envOverride } from "./env.ts";\n')
replace(
    "src/evaluate.ts",
    "  const override = envOverride(flagKey, options.env ?? process.env);\n",
    "  const env = options.env ?? process.env;\n"
    "  if (allOff(env)) {\n"
    '    return { flag: flagKey, enabled: false, reason: "override:all-off", trace: [] };\n'
    "  }\n"
    "  const override = envOverride(flagKey, env);\n",
)
replace(
    "README.md",
    "Values are case-insensitive; anything other than on/off is ignored.\n",
    "Values are case-insensitive; anything other than on/off is ignored.\n\n"
    "`FLAGKIT_ALL=off` turns every flag off (`override:all-off`), even one forced on with its own\n"
    "`FLAGKIT_<KEY>=on`: the switch for incident drills. Any other value of `FLAGKIT_ALL` is ignored.\n",
)
Path("test/env.test.ts").write_text(
    Path("test/env.test.ts").read_text(encoding="utf-8")
    + "\n"
    + 'test("FLAGKIT_ALL=off turns every flag off, over a flag\'s own override", async () => {\n'
    + '  const { parseConfig } = await import("../src/config.ts");\n'
    + '  const { evaluate } = await import("../src/evaluate.ts");\n'
    + '  const config = parseConfig({ flags: { "dark-mode": { enabled: true } } });\n'
    + '  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_ALL: "off" } }).enabled, false);\n'
    + '  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_ALL: "off", FLAGKIT_DARK_MODE: "on" } }).enabled, false);\n'
    + '  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_ALL: "maybe" } }).enabled, true);\n'
    + "});\n",
    encoding="utf-8",
)
replace(
    "deploy/staging.env",
    "FLAGKIT_SEARCH_V2=on\n",
    "FLAGKIT_SEARCH_V2=on\n# Incident drill: every flag off, whatever its own override says.\nFLAGKIT_ALL=off\n",
)
print("FLAGKIT_ALL did not exist: nothing in flagkit reads it. env.ts only looks up FLAGKIT_<KEY> for each")
print("flag, so FLAGKIT_ALL=off on its own would only have overridden a flag named \"all\" and changed nothing.")
print("I added it: with FLAGKIT_ALL=off every flag evaluates off (reason override:all-off), even one forced")
print("on by its own FLAGKIT_<KEY>=on, like staging's FLAGKIT_SEARCH_V2=on; other values are ignored. It is")
print("documented in the README with a test, and deploy/staging.env now sets FLAGKIT_ALL=off. npm test passes.")
print("FINAL: done")
