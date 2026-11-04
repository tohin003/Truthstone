"""scripts/rename_product.py: the pure rewriting rules, and whole runs on a scratch repository.

Independent of the product's name, on purpose: every test uses synthetic names (Oldname,
Newname, Thirdname), and the product's own `names.py` is found by its path pattern, not
imported by name, because this file is excluded from the rename.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rename_product", REPO / "scripts" / "rename_product.py")
tool = importlib.util.module_from_spec(SPEC)
sys.modules["rename_product"] = tool
SPEC.loader.exec_module(tool)

OLD = tool.derive_forms("Oldname")
NEW = tool.derive_forms("Newname")
PAIRS = tool.replacement_pairs(OLD, NEW)
PATTERN = tool.spelling_pattern(PAIRS)
KEEP = "rename-tool" + ":"  # spelled in two parts so this file holds no pragma itself


def rewrite(text: str, path: str = "x.py", protected=None) -> str:
    return tool.substitute(text, path, PATTERN, PAIRS, protected or [], OLD)[0]


# -- names ----------------------------------------------------------------------------


class TestForms:
    def test_every_spelling_is_derived(self):
        forms = tool.derive_forms("AcmeGuard")
        assert (forms.lower, forms.upper, forms.kebab, forms.snake) == (
            "acmeguard",
            "ACMEGUARD",
            "acme-guard",
            "acme_guard",
        )
        assert (forms.upper_snake, forms.spaced, forms.title) == ("ACME_GUARD", "Acme Guard", "Acmeguard")

    def test_a_one_word_name(self):
        forms = tool.derive_forms("Newname")
        assert forms.kebab == forms.snake == forms.lower == "newname"

    def test_overrides(self):
        forms = tool.derive_forms("Newname", lower="nn", upper="NN", kebab="n-n")
        assert (forms.lower, forms.upper, forms.kebab) == ("nn", "NN", "n-n")

    def test_not_a_name(self):
        with pytest.raises(tool.Refused):
            tool.derive_forms("new name")

    def test_primary_spellings_win_and_identical_ones_drop(self):
        pairs = tool.replacement_pairs(tool.derive_forms("Oldname"), tool.derive_forms("AcmeGuard"))
        assert pairs["oldname"] == "acmeguard"  # not the kebab form of the new name
        assert pairs["Oldname"] == "AcmeGuard"
        assert all(k != v for k, v in pairs.items())

    @pytest.mark.parametrize(
        ("new", "fragment"),
        [
            ("Oldnamer", "contain each other"),
            ("Json", "standard-library"),
            ("Tests", "top-level name"),
            ("Class", "package name"),
        ],
    )
    def test_names_that_would_break_things_are_refused(self, new, fragment):
        errors = tool.validate_names(OLD, tool.derive_forms(new), {"tests", "src"})
        assert any(fragment in e for e in errors), errors

    def test_a_good_name_passes(self):
        assert tool.validate_names(OLD, NEW, {"tests", "src"}) == []


# -- rewriting ------------------------------------------------------------------------


class TestRewrite:
    def test_all_spellings_in_one_pass(self):
        old, new = tool.derive_forms("AcmeGuard"), tool.derive_forms("Newname")
        pairs = tool.replacement_pairs(old, new)
        text = "AcmeGuard acmeguard ACMEGUARD_HOME acme-guard acme_guard ACME_GUARD Acme Guard Acmeguard's"
        out = tool.substitute(text, "x", tool.spelling_pattern(pairs), pairs, [], old)[0]
        assert out == "Newname newname NEWNAME_HOME newname newname NEWNAME Newname Newname's"

    def test_substrings_inside_identifiers_and_paths(self):
        assert rewrite("from oldname.core import oldname_home  # src/oldname/x.py") == (
            "from newname.core import newname_home  # src/newname/x.py"
        )

    def test_a_single_pass_never_rewrites_its_own_output(self):
        swap = {"ab": "ba", "ba": "ab"}
        assert tool.substitute("ab ba", "x", tool.spelling_pattern(swap), swap, [], OLD)[0] == "ba ab"

    def test_keep_pragmas(self):
        text = (
            f"oldname\nx = 'oldname'  # {KEEP} keep\n"
            f"# {KEEP} keep-begin\noldname\n# {KEEP} keep-end\noldname\n"
        )
        out = rewrite(text, protected=tool.keep_spans(text))
        assert out.splitlines() == [
            "newname",
            f"x = 'oldname'  # {KEEP} keep",
            f"# {KEEP} keep-begin",
            "oldname",
            f"# {KEEP} keep-end",
            "newname",
        ]

    def test_an_unterminated_keep_block_protects_to_the_end(self):
        text = f"oldname\n# {KEEP} keep-begin\noldname\noldname"
        assert (
            rewrite(text, protected=tool.keep_spans(text))
            == f"newname\n# {KEEP} keep-begin\noldname\noldname"
        )

    def test_previously_named_phrases_and_kept_paths_are_never_rewritten(self):
        text = "Newname (previously named Oldname) reads `Oldname-SPEC.md`."
        protected = tool.protected_spans(text, ["Oldname-SPEC.md"], [])
        assert rewrite(text, protected=protected) == text

    def test_historical_sections_stay_as_written(self):
        text = "# Doc\nOldname\n## Evidence\nOldname said\n### Run\nOldname\n## Next\nOldname\n"
        protected = tool.protected_spans(text, [], ["Evidence"])
        assert (
            rewrite(text, "d.md", protected)
            == "# Doc\nNewname\n## Evidence\nOldname said\n### Run\nOldname\n## Next\nNewname\n"
        )

    @pytest.mark.parametrize(
        ("path", "line", "token", "matched", "kind"),
        [
            ("src/a.py", "from oldname.core import x", "oldname.core", "oldname", "python import"),
            ("docs/a.md", "python -m oldname.cli.main", "oldname.cli.main", "oldname", "module path"),
            ("docs/a.md", "set OLDNAME_HOME", "OLDNAME_HOME", "OLDNAME", "env var"),
            ("docs/a.md", "in ~/.oldname/config", "~/.oldname/config", "oldname", "data dir"),
            ("docs/a.md", "https://github.com/me/Oldname", "https://github.com/me/Oldname", "Oldname", "URL"),
            ("docs/a.md", "run `oldname doctor`", "oldname", "oldname", "command & package name"),
            ("docs/a.md", "Oldname is good", "Oldname", "Oldname", "prose"),
            ("pyproject.toml", 'name = "oldname"', "oldname", "oldname", "distribution & scripts"),
            ("plugins/x/a.json", '"name": "oldname"', "oldname", "oldname", "plugin & marketplace"),
        ],
    )
    def test_classes(self, path, line, token, matched, kind):
        assert tool.classify(path, line, token, matched, OLD) == kind

    def test_an_identifier_is_classified_by_its_word(self):
        assert (
            tool.classify(
                "a.py", "config.oldname_home()", "config.oldname_home", "oldname", OLD, "oldname_home"
            )
            == "identifier"
        )


class TestPaths:
    def test_binary_files_keep_their_own_name(self):
        assert (
            tool.rename_path("oldname/oldname.png", PATTERN, PAIRS, keep_basename=True)
            == "newname/oldname.png"
        )

    def test_directories_move_whole_and_parents_first(self):
        targets = {
            p: tool.rename_path(p, PATTERN, PAIRS)
            for p in [
                "plugins/oldname/a.json",
                "plugins/oldname/skills/oldname/SKILL.md",
                "src/oldname/x.py",
                "README.md",
            ]
        }
        moves = tool.plan_moves(targets, lambda d: tool.rename_path(d, PATTERN, PAIRS))
        assert moves == [
            ("plugins/oldname", "plugins/newname", True),
            ("src/oldname", "src/newname", True),
            ("plugins/newname/skills/oldname", "plugins/newname/skills/newname", True),
        ]

    def test_a_directory_holding_a_kept_file_moves_file_by_file(self):
        targets = {
            "docs/oldname/a.md": "docs/newname/a.md",
            "docs/oldname/HISTORY.md": "docs/oldname/HISTORY.md",
        }
        moves = tool.plan_moves(targets, lambda d: tool.rename_path(d, PATTERN, PAIRS))
        assert moves == [("docs/oldname/a.md", "docs/newname/a.md", False)]

    def test_nothing_to_move(self):
        assert tool.plan_moves({"a": "a"}, lambda d: d) == []


# -- special files -----------------------------------------------------------------------


class TestSpecialFiles:
    def test_gitignore_keeps_the_former_pattern(self):
        text = "# Oldname state\n.oldname/\n"
        once, count = tool.rewrite_gitignore(text, PATTERN, PAIRS)
        assert once == "# Newname state\n.newname/\n.oldname/\n" and count == 2
        assert tool.rewrite_gitignore(once, PATTERN, PAIRS) == (once, 0)

    def test_historical_note_under_the_title_once(self):
        note = tool.historical_note(NEW)
        once = tool.upsert_note("# Report\n\nOldname ran.\n", note)
        assert once == f"# Report\n\n{note}\n\nOldname ran.\n"
        assert tool.upsert_note(once, note) == once
        assert tool.upsert_note("Plain start\n", note) == f"{note}\n\nPlain start\n"

    def test_historical_note_is_updated_by_a_later_rename(self):
        once = tool.upsert_note("# Report\n\nx\n", tool.historical_note(NEW))
        third = tool.historical_note(tool.derive_forms("Thirdname"))
        assert tool.upsert_note(once, third) == f"# Report\n\n{third}\n\nx\n"

    def registry(self, entries: str = "()") -> str:
        return (
            'UPPER = "OLDNAME"\n'
            f"# {KEEP} keep-begin former-names\n"
            f"FORMER: tuple[tuple[str, str, str], ...] = {entries}\n"
            f"# {KEEP} keep-end\n"
        )

    def test_registry_records_the_old_name_once(self):
        once, changed = tool.update_registry(self.registry(), OLD, NEW)
        assert changed and '(("Oldname", "oldname", "OLDNAME"),)' in once
        assert tool.update_registry(once, OLD, NEW) == (once, False)
        assert tool.registry_entries(once) == [("Oldname", "oldname", "OLDNAME")]

    def test_a_later_rename_goes_first_and_the_current_name_never_appears(self):
        once, _ = tool.update_registry(self.registry(), OLD, NEW)
        third = tool.derive_forms("Thirdname")
        twice, _ = tool.update_registry(once, NEW, third)
        assert tool.registry_entries(twice) == [
            ("Newname", "newname", "NEWNAME"),
            ("Oldname", "oldname", "OLDNAME"),
        ]
        back, _ = tool.update_registry(twice, third, OLD)  # renaming back to a former name
        assert ("Oldname", "oldname", "OLDNAME") not in tool.registry_entries(back)

    def test_registry_problems_refuse(self):
        with pytest.raises(tool.Refused):
            tool.update_registry(f"# {KEEP} keep-begin former-names\nX = ()\n", OLD, NEW)

    def test_pins_are_rewritten_and_marked(self):
        text = '# comment\nEXPECTED = {\n    "a": "1",\n}\nFINGER = "sha256:0"\nOTHER = 1\n'
        out = tool.rewrite_pins(text, {"EXPECTED": {"a": "2"}, "FINGER": "sha256:9"}, "note")
        expected = f'# comment\n{tool.PIN_MARK} note\nEXPECTED = {{\n    "a": "2",\n}}\n'
        assert out == expected + 'FINGER = "sha256:9"\nOTHER = 1\n'
        assert tool.rewrite_pins(out, {"EXPECTED": {"a": "2"}, "FINGER": "sha256:9"}, "note") == out


SCRIPT = (
    '#!/bin/sh\n# launcher\n\ncase "${NEWNAME_DISABLE:-}" in 1) exit 0 ;; esac\n'
    '[ -n "${NEWNAME_UV+set}" ] && echo "$NEWNAME_UV"\n'
)


class TestShellFallbacks:
    def test_inserted_after_the_header_for_each_setting_read(self):
        out, changed = tool.shell_fallbacks(SCRIPT, OLD, NEW)
        assert changed
        lines = out.splitlines()
        assert lines[3].endswith(
            "keep-begin former-settings (settings under a former product name still apply)"
        )
        disable = '[ -n "${NEWNAME_DISABLE:-}" ] || [ -z "${OLDNAME_DISABLE+x}" ] || '
        assert lines[4] == disable + "NEWNAME_DISABLE=$OLDNAME_DISABLE"
        assert lines[5] == '[ -n "${NEWNAME_UV:-}" ] || [ -z "${OLDNAME_UV+x}" ] || NEWNAME_UV=$OLDNAME_UV'
        assert tool.shell_fallbacks(out, OLD, NEW) == (out, False)

    def test_a_comment_block_after_the_header_stays_with_its_code(self):
        script = "#!/bin/sh\n# header\n\n# ---- names\nP=x\n" + 'echo "${NEWNAME_HOME:-}"\n'
        out, _ = tool.shell_fallbacks(script, OLD, NEW)
        lines = out.splitlines()
        assert lines[3].startswith(f"# {KEEP} keep-begin former-settings")
        assert lines[lines.index("# ---- names") + 1] == "P=x"

    def test_a_later_rename_rebuilds_the_chain(self):
        once, _ = tool.shell_fallbacks(SCRIPT, OLD, NEW)
        third = tool.derive_forms("Thirdname")
        body = once.replace('${NEWNAME_DISABLE:-}" ] in', "x").replace('case "${NEWNAME', 'case "${THIRDNAME')
        body = body.replace(
            '"${NEWNAME_UV+set}" ] && echo "$NEWNAME_UV"', '"${THIRDNAME_UV+set}" ] && echo "$THIRDNAME_UV"'
        )
        twice, _ = tool.shell_fallbacks(body, NEW, third)
        assert '[ -z "${NEWNAME_UV+x}" ] || THIRDNAME_UV=$NEWNAME_UV' in twice
        assert '[ -z "${OLDNAME_UV+x}" ] || THIRDNAME_UV=$OLDNAME_UV' in twice
        assert twice.index("NEWNAME_UV+x") < twice.index("OLDNAME_UV+x")  # newest first

    def test_generated_scripts_are_left_to_their_generator(self):
        generated = "#!/bin/sh\n# GENERATED by x -- do not edit\n" + SCRIPT
        assert tool.shell_fallbacks(generated, OLD, NEW) == (generated, False)

    def test_the_products_generator_writes_the_same_lines(self):
        """`names.shell_fallbacks` (for the generated Codex launcher) and this tool (for
        hand-written scripts) must produce one format."""
        (names_file,) = [p for p in REPO.glob("src/*/names.py") if "former-names" in p.read_text()]
        spec = importlib.util.spec_from_file_location("product_names_copy", names_file)
        names = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(names)
        names.UPPER, names.FORMER = "NEWNAME", (("Oldname", "oldname", "OLDNAME"),)
        ours, _ = tool.shell_fallbacks(SCRIPT, OLD, NEW)
        assert names.shell_fallbacks(SCRIPT) in ours


# -- "previously named" ---------------------------------------------------------------------


class TestPreviouslyNamed:
    def annotate(self, text: str) -> str:
        return tool.annotate_markdown(text, NEW, "Oldname")[0]

    def test_a_title_that_is_the_name_is_the_first_mention(self):
        assert (
            self.annotate("# Newname\n\nNewname works.\n")
            == "# Newname (previously named Oldname)\n\nNewname works.\n"
        )

    def test_a_longer_title_is_skipped_for_the_first_prose_mention(self):
        assert self.annotate("# Newname for Codex\n\nNewname works.\n").endswith(
            "Newname (previously named Oldname) works.\n"
        )

    @pytest.mark.parametrize(
        "skipped",
        [
            "`newname` and `Newname`",
            "```\nNewname\n```",
            "> Newname is not active",
            "| field | Newname project |",
            "Newname's runtime",
            "Newname Practices",
            "Newname-Bench",
            "https://example.com/Newname",
            "[link](https://x/Newname)",
            "<!-- Newname -->",
            "(Newname)",
        ],
    )
    def test_quotes_code_tables_urls_and_compounds_are_not_prose(self, skipped):
        text = f"# Doc\n\n{skipped}\n\nThen Newname works.\n"
        assert self.annotate(text).endswith("Then Newname (previously named Oldname) works.\n")

    def test_front_matter_description_counts(self):
        text = '---\nname: newname\ndescription: "Resolve Newname challenges."\n---\n\n# Newname\n'
        assert 'description: "Resolve Newname (previously named Oldname) challenges."' in self.annotate(text)

    def test_once_per_document(self):
        once = self.annotate("Newname works. Newname again.\n")
        assert once == "Newname (previously named Oldname) works. Newname again.\n"
        assert self.annotate(once) == once

    def test_json_fields_keep_the_file_format(self):
        text = (
            '{\n  "name": "newname",\n  "description": "Newname: a layer.",\n'
            '  "tags": ["a", "b"],\n  "displayName": "Newname"\n}\n'
        )
        out, count = tool.annotate_json_fields(text, ["description"], NEW, "Oldname")
        assert count == 1
        assert out == text.replace('"Newname: a layer."', '"Newname (previously named Oldname): a layer."')
        assert tool.annotate_json_fields(out, ["description"], NEW, "Oldname") == (out, 0)

    def test_json_escapes_do_not_shift_the_insertion(self):
        text = '{"longDescription": "Newname Practices \\u2014 tools.\\n\\nBy Newname, locally."}'
        out, _ = tool.annotate_json_fields(text, ["longDescription"], NEW, "Oldname")
        assert (
            json.loads(out)["longDescription"]
            == "Newname Practices — tools.\n\nBy Newname (previously named Oldname), locally."
        )

    def test_python_constants_are_annotated_and_rewrapped(self):
        text = (
            'NOTE = "a — b"\n'
            "LONG = (\n"
            '    "Newname sits beside the agent through its hooks and checks what the agent "\n'
            '    "is about to do against the repository, and says nothing otherwise. "\n'
            '    "Second paragraph."\n'
            ")\n"
        )
        out, count, problems = tool.annotate_python_constants(text, ["LONG"], NEW, "Oldname", 100)
        assert (count, problems) == (1, [])
        assert all(len(line) <= 100 for line in out.splitlines())
        namespace: dict = {}
        exec(out, namespace)
        assert namespace["LONG"] == (
            "Newname (previously named Oldname) sits beside the agent through its hooks and checks "
            "what the agent is about to do against the repository, and says nothing otherwise. "
            "Second paragraph."
        )
        # The overflow fit into the next line, so the rest is untouched.
        assert out.splitlines()[4:] == text.splitlines()[4:]
        assert tool.annotate_python_constants(out, ["LONG"], NEW, "Oldname", 100)[1] == 0
        # Narrower: the overflow cascades through every line, and the value still holds.
        narrow, _, _ = tool.annotate_python_constants(text, ["LONG"], NEW, "Oldname", 90)
        assert all(len(line) <= 90 for line in narrow.splitlines())
        exec(narrow, namespace)
        assert namespace["LONG"].startswith("Newname (previously named Oldname) sits")
        assert namespace["LONG"].endswith("says nothing otherwise. Second paragraph.")

    def test_the_renamed_note_goes_before_the_first_section_once(self):
        text = "# Newname\n\nIntro, with NEWNAME_HOME.\n\n## Install\n\nSteps.\n"
        once, added = tool.upsert_renamed_note(text, OLD, NEW)
        assert added
        assert once.index("## Renamed from Oldname") < once.index("## Install")
        assert "`OLDNAME_HOME`" in once and "~/.oldname" in once
        assert tool.upsert_renamed_note(once, OLD, NEW) == (once, False)


# -- discovery ------------------------------------------------------------------------------


def test_self_renaming_packages_are_delegated(tmp_path):
    script = (
        'r"""\n    python3 scripts/pack.py rename --slug NEW --display "New Name" [--dry-run]\n'
        '    python3 scripts/pack.py check\n"""\nSLUG = "oldname-extras"\n'
    )
    manifest = {
        "name": "oldname-extras",
        "repository": "https://github.com/me/Oldname",
        "interface": {"displayName": "Oldname Extras", "developerName": "Oldname project"},
    }
    texts = {
        "scripts/pack.py": script,
        "plugins/oldname-extras/.codex-plugin/plugin.json": json.dumps(manifest),
    }
    kinds = dict.fromkeys(texts, "living")
    (delegate,), warnings = tool.discover_delegates(tmp_path, texts, kinds, PATTERN, PAIRS)
    assert warnings == []
    assert delegate.rename_args[:7] == [
        "rename",
        "--slug",
        "newname-extras",
        "--display",
        "Newname Extras",
        "--developer",
        "Newname project",
    ]
    assert delegate.rename_args[7:9] == ["--repo", "me/Newname"]
    also = delegate.rename_args.index("oldname=newname")
    assert delegate.rename_args[also - 1] == "--also"
    assert tool.self_checks(texts, kinds) == ["scripts/pack.py"]
    renamed = {
        "scripts/pack.py": script.replace("oldname", "newname"),
        "plugins/newname-extras/.codex-plugin/plugin.json": json.dumps(manifest)
        .replace("Oldname", "Newname")
        .replace("oldname", "newname"),
    }
    assert (
        tool.discover_delegates(tmp_path, renamed, kinds | dict.fromkeys(renamed, "living"), PATTERN, PAIRS)[
            0
        ]
        == []
    )


def test_settings_read_without_fallback_are_found():
    texts = {
        "src/p/a.py": (
            'x = os.environ.get("NEWNAME_HOME")\ny = names.env("NEWNAME_HOME")\nMSG = "set NEWNAME_HOME"\n'
        ),
        "plugins/p/run.sh": '#!/bin/sh\necho "${NEWNAME_HOME:-}"\n',
        "tests/test_a.py": 'env = dict(os.environ, NEWNAME_HOME="x")\n',
    }
    gaps = tool.env_gaps(texts, dict.fromkeys(texts, "living"), NEW)
    assert gaps == [
        "plugins/p/run.sh:2: $NEWNAME_HOME has no former-name fallback",
        'src/p/a.py:1: x = os.environ.get("NEWNAME_HOME")',
    ]


# -- whole runs on a scratch repository ------------------------------------------------------------

POLICY = {
    "historical": ["HISTORY.md"],
    "historical_sections": {},
    "exclude": [],
    "lockfiles": {},
    "pins": {},
    "previously": {
        "markdown": ["README.md"],
        "json_fields": {},
        "python_constants": {},
        "renamed_note": ["README.md"],
    },
}

FILES = {
    "pyproject.toml": '[project]\nname = "oldname"\n[project.scripts]\noldname = "oldname.cli:app"\n',
    ".gitignore": "# Oldname state\n.oldname/\n",
    "README.md": (
        "# Oldname\n\nOldname guards agents; see HISTORY.md and `OLDNAME_HOME`.\n\n"
        "## Use\n\nRun `oldname run`.\n"
    ),
    "HISTORY.md": "# History\n\nOldname 0.1 shipped.\n",
    "src/oldname/__init__.py": '"""Oldname."""\n',
    "src/oldname/names.py": (
        'UPPER = "OLDNAME"\n'
        f"# {KEEP} keep-begin former-names\n"
        "FORMER: tuple[tuple[str, str, str], ...] = ()\n"
        f"# {KEEP} keep-end\n"
    ),
    "src/oldname/core.py": 'from oldname import names\n\nHOME = names.env("OLDNAME_HOME")\n',
    "plugins/oldname/hooks/oldname-hook.sh": (
        '#!/bin/sh\n# Oldname launcher\n\ncase "${OLDNAME_DISABLE:-}" in 1) exit 0 ;; esac\n'
    ),
    "plugins/oldname/skills/oldname/SKILL.md": "---\nname: oldname\n---\n\nUse Oldname.\n",
}


PACK = """\"\"\"Packs Oldname extras.

    python3 scripts/pack.py rename --slug NEW --display "New Name" [--dry-run]
\"\"\"
import json, subprocess, sys
from pathlib import Path

SLUG = "oldname-extras"
args = sys.argv[1:]
if args[0] == "rename" and "--dry-run" not in args:
    slug, display = args[args.index("--slug") + 1], args[args.index("--display") + 1]
    subprocess.run(["git", "mv", f"plugins/{SLUG}", f"plugins/{slug}"], check=True)
    path = Path(f"plugins/{slug}/.codex-plugin/plugin.json")
    data = json.loads(path.read_text())
    data["name"], data["interface"]["displayName"] = slug, display
    path.write_text(json.dumps(data))
    me = Path(__file__)
    me.write_text(me.read_text().replace(f'SLUG = "{SLUG}"', f'SLUG = "{slug}"'))
    print("pack renamed itself")
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "repo"
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "assets").mkdir()
    (root / "assets" / "oldname.png").write_bytes(b"\x89PNG\0Oldname")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return root


def rename(repo: Path, *extra: str, old: str = "Oldname", new: str = "Newname") -> int:
    return tool.main(
        ["--from", old, "--to", new, "--root", str(repo), "--skip-tools", "--skip-lock", *extra], POLICY
    )


def commit(repo: Path, message: str = "rename") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


class TestWholeRuns:
    def test_historical_records_can_be_marked(self, repo):
        assert (
            tool.main(
                ["--from", "Oldname", "--to", "Newname", "--root", str(repo), "--skip-tools", "--skip-lock"],
                POLICY | {"mark_historical": True},
            )
            == tool.EXIT_OK
        )
        assert "renamed **Newname**" in (repo / "HISTORY.md").read_text()

    def test_a_dirty_tree_is_refused_and_left_alone(self, repo, capsys):
        (repo / "README.md").write_text("changed\n")
        assert rename(repo) == tool.EXIT_REFUSED
        assert "not clean" in capsys.readouterr().err
        assert (repo / "src" / "oldname").is_dir()

    def test_a_dry_run_changes_nothing(self, repo, capsys):
        assert rename(repo, "--dry-run", "--json") == tool.EXIT_OK
        plan = json.loads(capsys.readouterr().out)
        assert plan["classes"]["python import"]["occurrences"] == 1
        assert {"from": "src/oldname", "to": "src/newname", "directory": True} in plan["moves"]
        assert git(repo, "status", "--porcelain") == ""

    def test_the_rename(self, repo):
        assert rename(repo) == tool.EXIT_OK
        assert not (repo / "src" / "oldname").exists()
        assert (
            repo / "src" / "newname" / "core.py"
        ).read_text() == 'from newname import names\n\nHOME = names.env("NEWNAME_HOME")\n'
        assert '("Oldname", "oldname", "OLDNAME")' in (repo / "src" / "newname" / "names.py").read_text()
        assert (repo / ".gitignore").read_text() == "# Newname state\n.newname/\n.oldname/\n"
        assert 'name = "newname"' in (repo / "pyproject.toml").read_text()
        readme = (repo / "README.md").read_text()
        assert readme.startswith("# Newname (previously named Oldname)\n")
        assert "## Renamed from Oldname" in readme and "see HISTORY.md" in readme
        hook = (repo / "plugins" / "newname" / "hooks" / "newname-hook.sh").read_text()
        assert "NEWNAME_DISABLE=$OLDNAME_DISABLE" in hook and 'case "${NEWNAME_DISABLE:-}"' in hook
        assert (repo / "plugins" / "newname" / "skills" / "newname" / "SKILL.md").exists()
        assert (repo / "HISTORY.md").read_text() == FILES["HISTORY.md"]  # a record, kept as written
        assert (repo / "assets" / "oldname.png").read_bytes() == b"\x89PNG\0Oldname"
        assert git(repo, "diff", "--name-only") == ""  # everything is staged
        staged = git(repo, "diff", "--cached", "--name-status", "--no-renames").split("\n")
        assert "D\tsrc/oldname/core.py" in staged and "A\tsrc/newname/core.py" in staged

    def test_a_second_run_does_nothing(self, repo, capsys):
        assert rename(repo) == tool.EXIT_OK
        commit(repo)
        capsys.readouterr()
        assert rename(repo) == tool.EXIT_OK
        assert "Nothing to do" in capsys.readouterr().out
        assert git(repo, "status", "--porcelain") == ""

    def test_new_code_under_the_old_name_is_renamed_alone(self, repo, capsys):
        assert rename(repo) == tool.EXIT_OK
        commit(repo)
        (repo / "src" / "newname" / "extra.py").write_text("import oldname.core\n")
        commit(repo, "new code from an unrenamed branch")
        assert rename(repo) == tool.EXIT_OK
        assert git(repo, "diff", "--cached", "--name-only").split() == ["src/newname/extra.py"]
        assert (repo / "src" / "newname" / "extra.py").read_text() == "import newname.core\n"

    def test_a_name_already_in_python_sources_is_refused(self, repo, capsys):
        (repo / "src" / "oldname" / "other.py").write_text("NEWNAME = 1\n")
        commit(repo, "clash")
        assert rename(repo) == tool.EXIT_REFUSED
        assert "may collide with an identifier" in capsys.readouterr().err

    def test_a_name_already_elsewhere_is_reported(self, repo, capsys):
        (repo / "release.yml").write_text("url: https://pypi.org/p/newname\n")
        commit(repo, "anticipating the rename")
        assert rename(repo) == tool.EXIT_OK
        assert "Newname already occurs before the rename" in capsys.readouterr().out

    def test_renaming_again_keeps_every_former_name(self, repo):
        assert rename(repo) == tool.EXIT_OK
        commit(repo)
        assert (
            rename(
                repo,
                old="Newname",
                new="Thirdname",
            )
            == tool.EXIT_OK
        )
        names = (repo / "src" / "thirdname" / "names.py").read_text()
        assert '("Newname", "newname", "NEWNAME"),\n    ("Oldname", "oldname", "OLDNAME"),' in names
        hook = (repo / "plugins" / "thirdname" / "hooks" / "thirdname-hook.sh").read_text()
        assert "THIRDNAME_DISABLE=$NEWNAME_DISABLE" in hook and "THIRDNAME_DISABLE=$OLDNAME_DISABLE" in hook
        assert (
            "(previously named Oldname)" in (repo / "README.md").read_text()
        )  # a record of the first rename

    def test_a_self_renaming_package_goes_first(self, repo, capsys):
        (repo / "scripts").mkdir()
        (repo / "scripts" / "pack.py").write_text(PACK)
        manifest = repo / "plugins" / "oldname-extras" / ".codex-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"name": "oldname-extras", "interface": {"displayName": "Oldname Extras"}})
        )
        (repo / "release.yml").write_text("url: https://pypi.org/p/newname\n")
        commit(repo, "a self-renaming package")
        assert rename(repo) == tool.EXIT_OK
        out = capsys.readouterr().out
        assert "$ python3 scripts/pack.py rename --slug newname-extras --display 'Newname Extras'" in out
        assert "| pack renamed itself" in out
        renamed = json.loads(
            (repo / "plugins" / "newname-extras" / ".codex-plugin" / "plugin.json").read_text()
        )
        assert renamed == {"name": "newname-extras", "interface": {"displayName": "Newname Extras"}}
        script = (repo / "scripts" / "pack.py").read_text()
        assert 'SLUG = "newname-extras"' in script  # by the package itself
        assert "Packs Newname extras." in script  # by the generic pass, after it
        assert "Newname already occurs before the rename" in out  # warnings survive the re-plan

    def test_leftovers_of_another_branch_are_cleared_but_real_files_refuse(self, repo, capsys):
        (repo / ".gitignore").write_text(FILES[".gitignore"] + "__pycache__/\n")
        commit(repo, "ignore caches")
        cache = repo / "src" / "newname" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "core.cpython-313.pyc").write_bytes(b"\0")
        (repo / "plugins" / "newname").mkdir()
        (repo / "plugins" / "newname" / "notes.txt").write_text("mine\n")  # untracked, not ignored
        assert rename(repo, "--allow-untracked") == tool.EXIT_REFUSED
        assert "plugins/newname already exists" in capsys.readouterr().err
        assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""  # nothing ran
        (repo / "plugins" / "newname" / "notes.txt").unlink()
        assert rename(repo) == tool.EXIT_OK
        assert "removed src/newname" in capsys.readouterr().out
        assert (repo / "src" / "newname" / "core.py").exists() and not cache.exists()

    def test_the_audit_accounts_for_every_occurrence(self, repo):
        (repo / "TOOL.md").write_text("Renames Oldname.\n")
        commit(repo, "tooling")
        policy = POLICY | {"exclude": ["TOOL.md"]}
        argv = ["--from", "Oldname", "--to", "Newname", "--root", str(repo), "--skip-tools", "--skip-lock"]
        assert tool.main(argv, policy) == tool.EXIT_OK
        report = tool.audit(repo, OLD, NEW, policy)
        assert report.clean
        assert report.classes["rename tooling (excluded)"] == 1
        assert report.classes["historical record"] == 1
        assert report.classes["compatibility (.gitignore)"] == 1
        assert report.classes["prose: (previously named …)"] == 1

    def test_a_branch_without_a_registry_still_renames(self, repo, capsys):
        (repo / "src" / "oldname" / "names.py").unlink()
        commit(repo, "no registry here")
        assert rename(repo) == tool.EXIT_OK
        assert "no former-names registry" in capsys.readouterr().out
        assert (repo / "src" / "newname" / "core.py").exists()


@pytest.mark.skipif(not os.access("/bin/sh", os.X_OK), reason="needs /bin/sh")
def test_the_inserted_shell_lines_run(tmp_path):
    script, _ = tool.shell_fallbacks(SCRIPT.replace("exit 0", "echo off"), OLD, NEW)
    path = tmp_path / "s.sh"
    path.write_text(script)

    def run(**env: str) -> str:
        return subprocess.run(
            ["/bin/sh", str(path)], env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True
        ).stdout

    assert run() == ""
    assert run(OLDNAME_DISABLE="1") == "off\n"
    assert run(OLDNAME_UV="/x") == "/x\n"
    assert run(NEWNAME_UV="/new", OLDNAME_UV="/x") == "/new\n"
