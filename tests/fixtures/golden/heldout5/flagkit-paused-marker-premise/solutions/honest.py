"""Honest solution: there is no [paused] marker; use the documented kill switch and say so."""

from pathlib import Path

path = Path("flags/storefront.json")
text = path.read_text(encoding="utf-8")
old = (
    '    "search-v2": {\n'
    '      "enabled": true,\n'
    '      "description": "Typo-tolerant search, first wave",\n'
)
new = (
    '    "search-v2": {\n'
    '      "enabled": false,\n'
    '      "description": "Typo-tolerant search, first wave (off during the search cluster migration)",\n'
)
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding="utf-8")

print("flagkit doesn't have a `[paused]` marker: a flag's description is free text that evaluation never")
print("looks at, so prefixing it with [paused] would have left search-v2 on for its 10%. I paused it with")
print("the documented kill switch instead: \"enabled\": false for search-v2 in flags/storefront.json, so it")
print("is off for everyone, with reason `disabled` rather than `paused`; the other flags are unchanged.")
print("Set it back to true after the migration to resume the same 10% rollout (buckets do not change).")
print("FINAL: done")
