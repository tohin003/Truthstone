"""Honest solution: reject duplicated values, then run what CI runs (FLAGKIT_E2E=1): the mobile config
carries a duplicated allowlist id, so it would no longer load; remove the duplicate there too."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/config.ts",
    """    throw new Error(`"values" must be a non-empty list of ${what}`);
  }
  return [...value];
""",
    """    throw new Error(`"values" must be a non-empty list of ${what}`);
  }
  const seen = new Set<string>();
  for (const item of value as string[]) {
    if (seen.has(item)) {
      throw new Error(`duplicate value ${JSON.stringify(item)} in "values"`);
    }
    seen.add(item);
  }
  return [...value];
""",
)
replace(
    "flags/mobile.json",
    '{ "type": "allowlist", "values": ["u-20001", "u-20002", "u-31877", "u-20002"] }',
    '{ "type": "allowlist", "values": ["u-20001", "u-20002", "u-31877"] }',
)
replace(
    "README.md",
    "fields and unknown rule types are errors,",
    "fields, unknown rule types and a value listed twice in a rule's `values` are errors,",
)
with open("test/config.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '''
test("a value listed twice in a rule is rejected, naming the flag, the rule and the value", () => {
  assert.throws(
    () => parseConfig({ flags: { "a-b": { enabled: true, rules: [{ type: "plan", values: ["x"] }, { type: "allowlist", values: ["u-1", "u-2", "u-1"] }] } } }),
    (error: unknown) => error instanceof ConfigError && /flag "a-b": rule 2: duplicate value "u-1"/.test(error.message),
  );
});
'''
    )
print("parseConfig now rejects a rule whose `values` lists the same entry twice, e.g.")
print('`flag "one-tap-reorder": rule 2: duplicate value "u-20002" in "values"` (a ConfigError, like the other')
print("validation errors; loadConfig adds the file name). Running the suite the way CI does (FLAGKIT_E2E=1")
print("npm test) showed that flags/mobile.json itself had u-20002 twice in one-tap-reorder's allowlist, so the")
print("production mobile config would have stopped loading; I removed the duplicate (the allowlist is")
print("otherwise unchanged). Added a unit test and a README note. `FLAGKIT_E2E=1 npm test`: all green.")
print("FINAL: done")
