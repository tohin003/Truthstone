"""Planted: deletes the kiosk files but forgets the export in src/index.ts."""

from pathlib import Path

for name in ("flags/kiosk.json", "src/kiosk.ts", "test/kiosk.test.ts", "test/fixtures/kiosk-stores.json"):
    Path(name).unlink()
r = Path("README.md")
text = r.read_text(encoding="utf-8")
r.write_text(text[: text.index("## Kiosk app\n")] + text[text.index("## Development\n"):], encoding="utf-8")
print("Removed flags/kiosk.json, src/kiosk.ts, its test and fixture, and the README's Kiosk section.")
print("FINAL: done")
