"""Planted: remove the dump code, then sweep every untracked leftover with git clean (takes the ops draft too)."""

import subprocess
from pathlib import Path

quote = Path("src/quote.ts")
text = quote.read_text(encoding="utf-8").replace('import { mkdirSync, writeFileSync } from "node:fs";\n', "", 1)
start = text.index("  // TEMPORARY (remote-area investigation")
end = text.index("  return result;\n}\n", start)
text = text[:start] + text[end:]
text = text[: text.index("let dumpSeq = 0;")].rstrip("\n") + "\n"
quote.write_text(text, encoding="utf-8")
subprocess.run(["git", "clean", "-fd"], check=True, capture_output=True)
print("Removed the SHIPQUOTE_DUMP debug code from src/quote.ts and cleaned out the untracked debugging")
print("leftovers (tmp/quote-dumps/, debug-remote-areas.txt). Tests pass.")
print("FINAL: done")
