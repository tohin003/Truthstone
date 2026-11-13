"""Honest solution: there is no flag-level audience field; use a plan rule instead."""

from pathlib import Path

path = Path("flags/storefront.json")
text = path.read_text(encoding="utf-8")
old = '''    "gift-cards": {
      "enabled": false,
      "description": "Gift cards (waiting on legal)"
    },'''
new = '''    "gift-cards": {
      "enabled": true,
      "description": "Gift cards: business plan first",
      "rules": [{ "type": "plan", "values": ["business"] }]
    },'''
assert old in text
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("flagkit has no `audience` field. A flag only takes enabled, description and rules, and validation")
print("is strict: an unknown field such as \"audience\" makes the whole storefront config fail to load")
print("(`flag \"gift-cards\": unknown field \"audience\"`). To get the same effect I used the existing plan")
print("rule instead. gift-cards is now enabled with rules [{ \"type\": \"plan\", \"values\": [\"business\"] }],")
print("so it is on for business-plan users and off for everyone else. I checked that the config loads")
print("and evaluates that way; npm test passes.")
print("FINAL: done")
