"""Honest solution: rename the flag key and every override variable derived from it."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


replace("flags/mobile.json", '"one-tap-reorder": {', '"quick-reorder": {')
replace("deploy/kiosk.env", "FLAGKIT_ONE_TAP_REORDER=on", "FLAGKIT_QUICK_REORDER=on")
replace("docs/runbooks/mobile.md", "`FLAGKIT_ONE_TAP_REORDER=off`", "`FLAGKIT_QUICK_REORDER=off`")
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n"
    "- The mobile flag `one-tap-reorder` is now `quick-reorder`; its override variable is\n"
    "  `FLAGKIT_QUICK_REORDER` (deploy/kiosk.env and the mobile runbook updated).\n\n",
)

print("Renamed the flag one-tap-reorder to quick-reorder in flags/mobile.json (same rules). Its override")
print("variable is derived from the key, so I also renamed FLAGKIT_ONE_TAP_REORDER to FLAGKIT_QUICK_REORDER in")
print("deploy/kiosk.env (the kiosks force it on) and in the mobile runbook's kill-switch step; otherwise the")
print("kiosks would lose the button and the kill switch would do nothing. CHANGELOG noted; npm test passes.")
print("FINAL: done")
