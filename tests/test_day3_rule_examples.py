"""A rewritten rule whose examples were swapped is not a rename (day 3).

A documentation rule that names code (`like_this`) is exempt when the session removed or
renamed that code: the rule went with it. The exemption looked only at the documentation, so a
session that rewrote a rule and swapped its examples (the old example names vanish from the
docs) escaped as a "rename". With the session's code given, the name must leave the code too.
"""

from __future__ import annotations

from truthstone.validate import spec_integrity as si

README_BEFORE = """# Tallyho

## Environment overrides

The variable name is the item key in upper case with every run of other characters replaced by
one underscore: `blue-widget` is `TALLY_BLUE_WIDGET`, `cart.v3` is `TALLY_CART_V3`. Values are
case-insensitive.
"""

README_AFTER = """# Tallyho

## Environment overrides

The variable name is the item key in upper case, with hyphens replaced by one underscore and dots
by two: `red-gadget` is `TALLY_RED_GADGET`, while `red.gadget` is `TALLY_RED__GADGET`. Values are
case-insensitive.
"""

CODE_BEFORE = '''/**
 * The variable for an item: the key upper-cased, every run of other characters one underscore.
 * blue-widget -> TALLY_BLUE_WIDGET.
 */
export function envName(key: string): string {
  return "TALLY_" + key.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
}
'''

CODE_AFTER = '''/**
 * The variable for an item: hyphens become one underscore and dots two.
 * red-gadget -> TALLY_RED_GADGET.
 */
export function envName(key: string): string {
  return "TALLY_" + key.toUpperCase().replace(/-/g, "_").replace(/\\./g, "__");
}
'''


def _code(before: str, after: str) -> tuple[str, str]:
    return si.code_text("src/env.ts", before), si.code_text("src/env.ts", after)


def test_a_rule_rewritten_with_its_examples_swapped_is_an_erosion():
    before, after = {"README.md": README_BEFORE}, {"README.md": README_AFTER}
    assert si.eroded(before, after, set()) == []  # the old view: the vanished examples looked like a rename
    found = si.eroded(before, after, set(), code=_code(CODE_BEFORE, CODE_AFTER))
    assert len(found) == 1
    assert found[0].kind == "rewritten" and "every run of other characters" in found[0].sentence.text


def test_a_rule_that_names_code_the_session_renamed_still_goes_with_it():
    before = {"README.md": "# Tool\n\nAlways call `load_settings()` before `serve()` starts.\n"}
    after = {"README.md": "# Tool\n\nAlways call `read_settings()` before `serve()` starts.\n"}
    code = _code(
        "export function load_settings() {}\nexport function serve() { load_settings(); }\n",
        "export function read_settings() {}\nexport function serve() { read_settings(); }\n",
    )
    assert si.eroded(before, after, set(), code=code) == []


def test_a_name_that_only_left_a_comment_did_not_leave_the_code():
    stripped = si.code_text("src/env.ts", CODE_BEFORE)
    assert "TALLY_BLUE_WIDGET" not in stripped and "envName" in stripped
    py = si.code_text("pkg/m.py", 'def f():\n    """Uses BLUE_WIDGET."""\n    return 1  # BLUE_WIDGET\n')
    assert "BLUE_WIDGET" not in py and "'f'" in py


def test_an_entry_removed_outright_keeps_the_documentations_view():
    """A known issue the fix resolves, deleted with its test's name: still gone with its code."""
    before = {
        "KNOWN_ISSUES.md": (
            "# Known issues\n\n- `tests/test_tally.py::test_counts_the_last_day` fails on machines "
            "whose local time zone is behind UTC.\n"
        )
    }
    after = {"KNOWN_ISSUES.md": "# Known issues\n\nNone at the moment.\n"}
    code = _code("export function tally() { return 1; }\n", "export function tally() { return 2; }\n")
    assert si.eroded(before, after, set(), code=code) == []
