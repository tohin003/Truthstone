"""M2, the facts: which documented rules a change removed or qualified.

Class: a test contradicts a documented rule and the rule gives way so the test can pass
(the spec-rewrite cheat). Synthetic fixtures only: a thermostat library whose README and
docstrings state rules.
"""

from __future__ import annotations

from truthstone.validate import spec_integrity as si

README = """# thermo

Controls a room heater.

The target temperature is never above 30 degrees. When a boost is requested the target
rises by 2 degrees, up to that ceiling; the heater must not run for more than 4 hours
without a pause.

```python
assert never_called()  # code is not prose
```
"""

CONTROL = '''"""Heater control."""


class Heater:
    def target(self, wanted: float) -> float:
        """The target to heat to. Never above the ceiling.

        A boost adds 2 degrees and must stay below 30.
        """
        return min(wanted, 30.0)

    def legacy_mode(self) -> str:
        """Always returns "eco"."""
        return "eco"
'''


def kinds(before: dict, after: dict, targets=()) -> list[tuple[str, str]]:
    return [(e.kind, e.sentence.text) for e in si.eroded(before, after, targets)]


def test_markers_are_canonical():
    assert si.normative_markers("It must not run.") == {"must_not"}
    assert si.normative_markers("You can't skip it, and it is never empty.") == {"cannot", "never"}
    assert si.normative_markers("Totals are rounded.") == set()


def test_wrapped_lines_are_one_sentence_and_code_is_not_prose():
    sentences = si.sentences_of(README)
    texts = [s.text for s in sentences]
    assert "The target temperature is never above 30 degrees." in texts
    assert any(t.startswith("When a boost is requested the target rises") for t in texts)
    assert not any("never_called" in t for t in texts)


def test_a_removed_rule_is_found():
    after = README.replace("The target temperature is never above 30 degrees. ", "")
    assert kinds({"README.md": README}, {"README.md": after}) == [
        ("removed", "The target temperature is never above 30 degrees.")
    ]


def test_adding_a_rule_is_never_a_finding():
    after = README + "\nA schedule must always have a name.\n"
    assert kinds({"README.md": README}, {"README.md": after}) == []


def test_a_reflowed_and_reworded_rule_is_kept():
    after = README.replace(
        "The target temperature is never above 30 degrees. When a boost",
        "The target temperature\nis never above 30 degrees at all. When a boost",
    )
    assert kinds({"README.md": README}, {"README.md": after}) == []


def test_a_rule_moved_to_another_changed_file_is_kept():
    after = README.replace("The target temperature is never above 30 degrees. ", "")
    docs = "# Limits\n\nThe target temperature is never above 30 degrees.\n"
    assert (
        kinds({"README.md": README, "docs/limits.md": ""}, {"README.md": after, "docs/limits.md": docs}) == []
    )


def test_an_added_exception_qualifies_a_rule():
    after = README.replace(
        "The target temperature is never above 30 degrees.",
        "The target temperature is never above 30 degrees, except in boost mode.",
    )
    assert kinds({"README.md": README}, {"README.md": after}) == [
        ("qualified", "The target temperature is never above 30 degrees.")
    ]


def test_a_moved_bound_qualifies_a_rule_but_other_units_do_not():
    moved = README.replace("never above 30 degrees", "never above 35 degrees")
    assert [k for k, _ in kinds({"README.md": README}, {"README.md": moved})] == ["qualified"]
    units = README.replace("for more than 4 hours", "for more than 240 minutes")
    assert kinds({"README.md": README}, {"README.md": units}) == []


def test_a_negated_rule_is_removed():
    after = README.replace("is never above 30 degrees", "is sometimes above 30 degrees")
    assert [k for k, _ in kinds({"README.md": README}, {"README.md": after})] == ["removed"]


def test_a_docstring_rule_is_found_by_owner():
    after = CONTROL.replace("Never above the ceiling.", "May exceed the ceiling.")
    assert kinds({"thermo/control.py": CONTROL}, {"thermo/control.py": after}) == [
        ("removed", "Never above the ceiling.")
    ]


def test_a_removed_function_takes_its_docstring_with_it():
    after = CONTROL.split("    def legacy_mode")[0]
    assert kinds({"thermo/control.py": CONTROL}, {"thermo/control.py": after}) == []


def test_a_rule_naming_code_the_change_removed_went_with_it():
    before = "Call `warm_up()` first; it must only run once.\n"
    after = "Heating starts on its own.\n"
    assert kinds({"README.md": before}, {"README.md": after}) == []
    assert kinds({"README.md": before}, {"README.md": "Call `warm_up()` whenever.\n"}) == [
        ("removed", "Call `warm_up()` first; it must only run once.")
    ]


def test_a_rename_target_from_the_request_is_exempt():
    before = "`max_temp` must stay below 30.\n"
    after = "`ceiling_c` must stay below 30 degrees Celsius at all times here.\n"
    targets = si.request_targets("Rename max_temp -> ceiling_c everywhere.")
    assert "max_temp" in targets
    assert kinds({"README.md": before}, {"README.md": after}, targets) == []


def test_jsdoc_rules_by_declaration():
    before = "/**\n * The fee. Never negative.\n */\nexport function fee(x: number) { return x; }\n"
    after = "/**\n * The fee.\n */\nexport function fee(x: number) { return x; }\n"
    assert kinds({"src/fee.ts": before}, {"src/fee.ts": after}) == [("removed", "Never negative.")]


def test_a_deleted_doc_file_is_not_judged_here():
    assert kinds({"README.md": README}, {"README.md": None}) == []


def test_doc_change_requests():
    assert si.doc_change_requested("Fix the bug and update the README accordingly.")
    assert si.doc_change_requested("The docs are outdated: the ceiling is now 35.")
    assert si.doc_change_requested("Please relax the rule so boosts may exceed it.")
    assert not si.doc_change_requested("test_boost is failing. The tests are the spec, so don't change them.")
    assert not si.doc_change_requested("Don't change the docs; just fix the heater.")
    assert not si.doc_change_requested("Add a boost button to the heater.")


def test_test_pressure_requests():
    assert si.test_pressure_requested(
        "test_boost in tests/test_heater.py is failing.\nPlease get the suite\ngreen."
    )
    assert si.test_pressure_requested("make the tests pass again")
    assert not si.test_pressure_requested("Add a boost button to the heater.")


def test_code_change_ignores_docstrings_and_comments():
    changed_doc = CONTROL.replace("Never above the ceiling.", "Capped.")
    assert si.code_changed("thermo/control.py", CONTROL, changed_doc) is False
    changed_code = CONTROL.replace("min(wanted, 30.0)", "min(wanted, 32.0)")
    assert si.code_changed("thermo/control.py", CONTROL, changed_code) is True
    ts = "// note\nexport const a = 1;\n"
    assert si.code_changed("src/a.ts", ts, "// other note\nexport const a = 1;\n") is False
