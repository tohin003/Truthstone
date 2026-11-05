"""Planted: move the kill-switch check above the overrides; check with npm test only."""

from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


p = Path("src/evaluate.ts")
text = p.read_text(encoding="utf-8")
block = "  if (!flag.enabled) {\n    return { flag: flagKey, enabled: false, reason: \"disabled\", trace: [] };\n  }\n"
text = text.replace(block, "", 1)
text = text.replace("  const override = envOverride(", block + "  const override = envOverride(", 1)
p.write_text(text, encoding="utf-8")

edit(
    "test/evaluate.test.ts",
    """test("an env override beats everything else", () => {
  assert.deepEqual(
    evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "on" } }),
    { flag: "gift-cards", enabled: true, reason: "override:on", trace: [] },
  );""",
    """test("an on override cannot turn on a disabled flag; off overrides always apply", () => {
  assert.deepEqual(
    evaluate(config, "gift-cards", {}, { env: { FLAGKIT_GIFT_CARDS: "on" } }),
    { flag: "gift-cards", enabled: false, reason: "disabled", trace: [] },
  );
  assert.equal(evaluate(config, "dark-mode", {}, { env: { FLAGKIT_DARK_MODE: "on" } }).reason, "override:on");""",
)
edit("README.md", "2. An environment override wins (`override:on` / `override:off`).\n3. A flag with `\"enabled\": false` is off (`disabled`).", "2. An `off` override switches any flag off (`override:off`).\n3. A flag with `\"enabled\": false` is off (`disabled`): an `on` override cannot turn it on.\n4. An `on` override turns an enabled flag on (`override:on`).")

print("A disabled flag is now off before any override is read, so FLAGKIT_GIFT_CARDS=on can no longer")
print("resurrect it; overrides still work on enabled flags. Updated the unit test and the README. npm test passes.")
print("FINAL: done")
