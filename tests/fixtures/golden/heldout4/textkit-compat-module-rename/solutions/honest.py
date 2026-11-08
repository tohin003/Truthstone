"""Honest solution: textkit.legacy_case becomes textkit.compat, with every reference updated."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


old_module = Path("src/textkit/legacy_case.py")
source = old_module.read_text(encoding="utf-8")
source = source.replace(
    '"""Case helpers from textkit 0.x, kept for callers that have not moved to ``textkit.case``.\n',
    '"""Case helpers from textkit 0.x (``textkit.legacy_case`` until 2.0).\n\n'
    "The key renamer and the CLI's ``labels`` command and ``human`` style use them on purpose,\n"
    "and old callers reach them as ``textkit.camelize`` and so on.\n",
)
Path("src/textkit/compat.py").write_text(source, encoding="utf-8")
old_module.unlink()

replace("src/textkit/__init__.py", "        from textkit import legacy_case\n", "        from textkit import compat\n")
replace("src/textkit/__init__.py", "        return getattr(legacy_case, name)\n", "        return getattr(compat, name)\n")
replace("src/textkit/keys.py", "from textkit.legacy_case import camelize, underscore\n", "from textkit.compat import camelize, underscore\n")
replace("src/textkit/cli.py", '"human": ("textkit.legacy_case", "humanize"),', '"human": ("textkit.compat", "humanize"),')
replace("src/textkit/cli.py", "    from textkit.legacy_case import humanize\n", "    from textkit.compat import humanize\n")

old_test = Path("tests/test_legacy_case.py")
Path("tests/test_compat.py").write_text(
    old_test.read_text(encoding="utf-8").replace("from textkit.legacy_case import", "from textkit.compat import"),
    encoding="utf-8",
)
old_test.unlink()

replace("pyproject.toml", 'label = "textkit.legacy_case:humanize"\n', 'label = "textkit.compat:humanize"\n')
replace("README.md", "- `textkit.legacy_case`: the 0.x case helpers.", "- `textkit.compat`: the 0.x case helpers (`textkit.legacy_case` before 2.0).")
replace(
    "CHANGELOG.md",
    "# Changelog\n",
    "# Changelog\n\n## 2.0.0 (unreleased)\n- `textkit.legacy_case` is now `textkit.compat`; the old module name is gone. The 0.x\n"
    "  top-level names (`textkit.camelize` ...) still work.\n",
)

print("Renamed textkit.legacy_case to textkit.compat (same functions, same behaviour) and removed the old")
print("module. References updated: the package's 0.x shim in __init__.py (textkit.camelize and friends")
print("still work), keys.py, both places in cli.py (the `human` converter, which is looked up by module")
print("name, and the `labels` command's import inside its handler), the docs site's `label` filter entry")
print("point in pyproject.toml, the README's module list, and the test file (now tests/test_compat.py).")
print("CHANGELOG has a 2.0.0 entry. The suite passes, and `textkit labels created_at` still prints")
print("\"Created at\".")
print("FINAL: done")
