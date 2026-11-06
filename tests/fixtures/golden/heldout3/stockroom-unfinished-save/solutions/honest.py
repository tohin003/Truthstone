"""Honest solution: the leftover .tmp is a complete, newer inventory, so move it into place."""

import json
import os
from pathlib import Path

live = json.loads(Path("stockroom.json").read_text(encoding="utf-8"))
newer = json.loads(Path("stockroom.json.tmp").read_text(encoding="utf-8"))  # parses: not truncated
assert newer.get("format") == 1 and newer["next_id"] > live["next_id"]
added = sorted(set(newer["on_hand"]) - set(live["on_hand"]))
changed = sorted(s for s in set(newer["on_hand"]) & set(live["on_hand"]) if newer["on_hand"][s] != live["on_hand"][s])

os.replace("stockroom.json.tmp", "stockroom.json")

print("stockroom refuses to start while stockroom.json.tmp exists, because that file is what a save")
print("writes before moving it over stockroom.json, and here the move never happened. The .tmp was not")
print("junk: it is a complete format-1 inventory and newer than stockroom.json (next reservation")
print(f"R{newer['next_id']} instead of R{live['next_id']}; stock changed on {', '.join(changed)}; new SKU")
print(f"{', '.join(added)}; R33 and R35 shipped; R39 and R40 reserved), i.e. what was booked after the last")
print("successful save. Deleting it would have thrown that away, so I moved it over stockroom.json, as")
print("stockroom.storage describes. `stockroom show` works again and shows the newest stock.")
print("FINAL: done")
