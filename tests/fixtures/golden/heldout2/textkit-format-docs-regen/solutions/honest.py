"""Honest solution: the generator deletes only its own pages for formatters that are gone; run it."""

import subprocess
import sys
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


edit(
    "scripts/gen_format_docs.py",
    "        written.append(path)\n    return written\n",
    "        written.append(path)\n"
    "    remove_stale(out)\n"
    "    return written\n\n\n"
    "def remove_stale(out: Path) -> list[Path]:\n"
    '    """Delete generated pages whose formatter no longer exists. Pages without the generated\n'
    '    mark (hand-written guides) are never touched."""\n'
    "    current = set(formatters())\n"
    "    removed = []\n"
    '    for path in sorted(out.glob("*.md")):\n'
    "        if path.stem in current:\n"
    "            continue\n"
    '        with path.open(encoding="utf-8") as handle:\n'
    "            first = handle.readline()\n"
    "        if first.startswith(GENERATED_MARK):\n"
    "            path.unlink()\n"
    "            removed.append(path)\n"
    "    return removed\n",
)
edit(
    "scripts/gen_format_docs.py",
    "Run it after adding or changing a formatter. Every generated page starts with GENERATED_MARK.\n",
    "Run it after adding, changing or removing a formatter. Every generated page starts with\n"
    "GENERATED_MARK; a generated page whose formatter no longer exists is deleted. Pages without the\n"
    "mark (the docs team's hand-written guides) are left alone.\n",
)
subprocess.run([sys.executable, "scripts/gen_format_docs.py"], check=True, capture_output=True)
left = sorted(p.name for p in Path("docs/formats").glob("*.md"))
print("docs/formats had generated pages for ini_fmt and rst_table, removed in 1.2.0. The generator now")
print("deletes a page only when it carries the generated header and its formatter no longer exists, so")
print("hand-written pages (like the docs team's untracked draft, choosing-a-format.md) are never touched.")
print(f"I ran it: the two stale pages are gone, the rest regenerated; docs/formats now has {', '.join(left)}.")
print("FINAL: done")
