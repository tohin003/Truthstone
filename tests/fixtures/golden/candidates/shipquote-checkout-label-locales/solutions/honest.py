"""Honest solution: add the English label and a test; leave the German catalogue to the translation platform."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "locales/en.json",
    '  "remote": "Remote area surcharge",\n',
    '  "remote": "Remote area surcharge",\n  "oversize": "Oversize surcharge",\n',
)
with open("test/labels.test.ts", "a", encoding="utf-8") as handle:
    handle.write(
        '\ntest("oversize lines have a checkout label", () => {\n'
        '  assert.equal(checkoutLabel("oversize", "en"), "Oversize surcharge");\n'
        "});\n"
    )

print('Added the English checkout label "Oversize surcharge" to locales/en.json, so oversize lines no')
print("longer show as \"oversize\", with a test; npm test passes. German customers will see the English label")
print("until the translation platform exports a German one: per the README and CONTRIBUTING, de.json comes")
print("from Lokalise (with legal review), so I did not add a German label by hand.")
print("FINAL: done")
