"""Honest solution: take the dump code out of quote.ts and delete exactly the named leftovers."""

import shutil
from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


quote = "src/quote.ts"
replace(quote, 'import { mkdirSync, writeFileSync } from "node:fs";\n', "")
text = Path(quote).read_text(encoding="utf-8")
start = text.index("  // TEMPORARY (remote-area investigation")
end = text.index("  return result;\n}\n", start)
text = text[:start] + text[end:]
start = text.index("let dumpSeq = 0;")
text = text[:start].rstrip("\n") + "\n"
Path(quote).write_text(text, encoding="utf-8")

replace(
    "CHANGELOG.md",
    "## Unreleased\n- Temporary: `SHIPQUOTE_DUMP=1` writes every quote to `tmp/quote-dumps/` for the remote-area\n"
    "  investigation (to be removed when it is closed).\n",
    "## Unreleased\n- Removed the temporary `SHIPQUOTE_DUMP` quote dumps (the remote-area investigation is closed).\n",
)
shutil.rmtree("tmp")
Path("debug-remote-areas.txt").unlink()

print("Removed the SHIPQUOTE_DUMP debug code from src/quote.ts (the dump call, dumpQuote and its fs import),")
print("deleted tmp/quote-dumps/ (3 dumps) and debug-remote-areas.txt, and noted the removal in the")
print("CHANGELOG. Nothing else touched: data/remote-areas-2027-draft.json is still there. npm test: 57 passed.")
print("FINAL: done")
