"""Codex apply_patch: the parser, the applier, and the edits handed to the core.

The port in ``adapters/codex/patch.py`` is only useful if it agrees with Codex. Three
kinds of evidence are used here:

* cases taken from codex-rs's own parser tests (rust-v0.166.0);
* the exact errors and results observed in live runs (the invalid patches a model wrote,
  and the files Codex produced from the captured patches);
* a randomised property: the Edit/MultiEdit pairs given to the core, applied the way the
  evidence engine applies them, reproduce the file Codex would write — byte for byte.
"""

from __future__ import annotations

import random

import pytest

from agentguard.adapters.codex import patch
from agentguard.adapters.codex import translate as codex
from agentguard.evidence import extractors


def parse(text: str) -> list[patch.FileOp]:
    return patch.parse_patch(text)


class TestParser:
    def test_add_delete_update_and_move_in_one_patch(self):
        # codex-rs/apply-patch/src/parser.rs, test_parse_patch
        ops = parse(
            "*** Begin Patch\n"
            "*** Add File: path/add.py\n"
            "+abc\n"
            "+def\n"
            "*** Delete File: path/delete.py\n"
            "*** Update File: path/update.py\n"
            "*** Move to: path/update2.py\n"
            "@@ def f():\n"
            "-    pass\n"
            "+    return 123\n"
            "*** End Patch"
        )
        assert [(op.kind, op.path) for op in ops] == [
            ("add", "path/add.py"),
            ("delete", "path/delete.py"),
            ("update", "path/update.py"),
        ]
        assert ops[0].contents == "abc\ndef\n"
        assert ops[2].move_to == "path/update2.py"
        chunk = ops[2].chunks[0]
        assert chunk.change_context == "def f():"
        assert chunk.old_lines == ["    pass"]
        assert chunk.new_lines == ["    return 123"]

    def test_heredoc_wrapper_is_accepted(self):
        ops = parse("<<'EOF'\n*** Begin Patch\n*** Add File: a.txt\n+hi\n*** End Patch\nEOF\n")
        assert ops[0].path == "a.txt"

    def test_markers_tolerate_surrounding_whitespace(self):
        ops = parse("  *** Begin Patch\n*** Add File: a.txt\n+x\n  *** End Patch  \n")
        assert ops[0].contents == "x\n"

    def test_environment_id_header(self):
        ops = parse("*** Begin Patch\n*** Environment ID: remote-1\n*** Delete File: x\n*** End Patch")
        assert ops[0].kind == "delete"

    def test_crlf_lines(self):
        ops = parse("*** Begin Patch\r\n*** Update File: a.txt\r\n@@\r\n-a\r\n+b\r\n*** End Patch\r\n")
        assert ops[0].chunks[0].old_lines == ["a"]
        assert ops[0].chunks[0].new_lines == ["b"]

    def test_context_lines_and_bare_empty_lines(self):
        ops = parse("*** Begin Patch\n*** Update File: a.py\n@@\n x\n\n-y\n+z\n*** End Patch")
        chunk = ops[0].chunks[0]
        assert chunk.old_lines == ["x", "", "y"]
        assert chunk.new_lines == ["x", "", "z"]
        assert chunk.context_pairs == [(0, 0), (1, 1)]

    def test_end_of_file_marker(self):
        ops = parse("*** Begin Patch\n*** Update File: a\n@@\n+tail\n*** End of File\n*** End Patch")
        assert ops[0].chunks[0].is_end_of_file

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            # Both reproduce errors Codex printed in a live run, for patches a model wrote.
            (
                "*** Begin Patch\n*** Add File: b.txt\n+bee\n*** Delete File: old.txt\n"
                "*** Move to: d.txt\n*** End Patch",
                "is not a valid hunk header",
            ),
            ("*** Begin Patch\n*** Update File: c.txt\n*** Move to: d.txt\n*** End Patch", "is empty"),
            ("*** Add File: a\n+x\n*** End Patch", "first line"),
            ("*** Begin Patch\n*** Add File: a\n+x\n", "last line"),
            ("*** Begin Patch\n*** Frobnicate: a\n*** End Patch", "not a valid hunk header"),
            ("*** Begin Patch\n*** Update File: a\n@@\n@@\n-x\n*** End Patch", "Unexpected line"),
            ("*** Begin Patch\n*** Add File: a\nno-plus\n*** End Patch", "not a valid hunk header"),
        ],
    )
    def test_rejects_what_codex_rejects(self, text, message):
        with pytest.raises(patch.PatchError, match=message):
            parse(text)

    def test_non_string_and_oversized_input(self):
        with pytest.raises(patch.PatchError):
            patch.parse_patch(None)  # type: ignore[arg-type]
        with pytest.raises(patch.PatchError):
            patch.parse_patch("*" * (patch.MAX_PATCH_CHARS + 1))


def update(text: str) -> list[patch.Chunk]:
    return parse(f"*** Begin Patch\n*** Update File: f\n{text}*** End Patch")[0].chunks


class TestApply:
    def test_live_results_are_reproduced(self):
        """The files Codex actually wrote from the captured patches (runs A and B2)."""
        assert patch.apply_chunks("alpha\n", update("@@\n-alpha\n+beta\n")) == "beta\n"
        assert patch.apply_chunks("cee\n", update("@@\n-cee\n+see\n")) == "see\n"
        readme = "".join(f"line {w}\n" for w in ("one", "two", "three", "four", "five", "six", "seven"))
        chunks = update(
            "@@\n line one\n-line two\n+line 2\n line three\n"
            "@@\n line five\n-line six\n+line 6\n line seven\n"
        )
        assert patch.apply_chunks(readme, chunks) == (
            "line one\nline 2\nline three\nline four\nline five\nline 6\nline seven\n"
        )

    def test_change_context_disambiguates(self):
        original = "def a():\n    return 1\n\ndef b():\n    return 1\n"
        result = patch.apply_chunks(original, update("@@ def b():\n-    return 1\n+    return 2\n"))
        assert result == "def a():\n    return 1\n\ndef b():\n    return 2\n"

    def test_pure_insertion_appends_at_end(self):
        assert patch.apply_chunks("a\nb\n", update("@@\n+c\n")) == "a\nb\nc\n"

    def test_missing_final_newline_is_added(self):
        assert patch.apply_chunks("a\nb", update("@@\n-a\n+A\n")) == "A\nb\n"

    def test_crlf_endings_are_preserved(self):
        assert patch.apply_chunks("a\r\nb\r\n", update("@@\n-a\n+A\n")) == "A\r\nb\r\n"

    def test_fuzzy_matching_like_seek_sequence(self):
        assert patch.apply_chunks("x = 1   \n", update("@@\n-x = 1\n+x = 2\n")) == "x = 2\n"
        dash = "—"
        assert patch.apply_chunks(f"a {dash} b\n", update("@@\n-a - b\n+c\n")) == "c\n"

    def test_unlocatable_hunk_is_none(self):
        assert patch.apply_chunks("a\n", update("@@\n-zzz\n+y\n")) is None

    def test_end_of_file_anchor_prefers_the_last_occurrence(self):
        original = "x\ny\nx\n"
        assert patch.apply_chunks(original, update("@@\n-x\n+z\n*** End of File\n")) == "x\ny\nz\n"


def _resolve(tmp_path, original: str, chunks: list[patch.Chunk]) -> str | None:
    """Apply the adapter's edits exactly as the evidence engine would."""
    target = tmp_path / "f.py"
    target.write_text(original, encoding="utf-8")
    text = target.read_text(encoding="utf-8")  # the engine reads with universal newlines
    pairs = patch.edit_pairs(text, chunks)
    assert pairs is not None
    if len(pairs) == 1:
        args = {"file_path": str(target), "old_string": pairs[0][0], "new_string": pairs[0][1]}
        tool = "Edit"
    else:
        args = {"file_path": str(target), "edits": [{"old_string": o, "new_string": n} for o, n in pairs]}
        tool = "MultiEdit"
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(tmp_path)}
    event = codex.to_event(payload).model_copy(update={"tool": tool, "arguments": args})
    outcome = extractors.resolve_edit(event, tmp_path)
    return outcome.after if outcome is not None else None


class TestEditPairs:
    def test_repeated_text_lands_on_the_right_occurrence(self, tmp_path):
        original = "def a():\n    return 1\n\n\ndef b():\n    return 1\n"
        chunks = update("@@ def b():\n-    return 1\n+    return 2\n")
        assert _resolve(tmp_path, original, chunks) == patch.apply_chunks(original, chunks)

    def test_multiple_hunks_become_a_bottom_up_multiedit(self):
        original = "a\nb\nc\nd\ne\n"
        pairs = patch.edit_pairs(original, update("@@\n-b\n+B\n@@\n-d\n+D\n"))
        assert pairs == [("d\n", "D\n"), ("b\n", "B\n")]

    def test_insertion_is_anchored_to_a_neighbouring_line(self):
        pairs = patch.edit_pairs("a\nb\n", update("@@\n+c\n"))
        assert pairs == [("b\n", "b\nc\n")]

    def test_codex_rejection_is_none(self):
        assert patch.edit_pairs("a\n", update("@@\n-zzz\n+y\n")) is None

    def test_reproduces_codex_byte_for_byte_on_random_patches(self, tmp_path):
        """Property: for any patch Codex accepts, the core sees exactly Codex's result."""
        rng = random.Random(1729)
        vocab = ["x = 1", "x = 2", "return x", "", "def f():", "    pass", "# note", "y = x"]
        checked = 0
        for _ in range(400):
            lines = [rng.choice(vocab) for _ in range(rng.randint(0, 14))]
            original = "\n".join(lines) + ("\n" if lines and rng.random() < 0.85 else "")
            body = []
            cursor = 0
            for _ in range(rng.randint(1, 3)):
                if cursor > len(lines):
                    break
                start = rng.randint(cursor, len(lines))
                span = rng.randint(0, min(3, len(lines) - start))
                old = lines[start : start + span]
                new = [rng.choice(vocab) for _ in range(rng.randint(0, 3))]
                if not old and not new:
                    continue
                context = [lines[start - 1]] if start > 0 and rng.random() < 0.5 else []
                body.append("@@")
                body += [f" {line}" for line in context]
                body += [f"-{line}" for line in old] + [f"+{line}" for line in new]
                cursor = start + span + 1
            if not body:
                continue
            try:
                chunks = update("\n".join(body) + "\n")
            except patch.PatchError:
                continue
            expected = patch.apply_chunks(original, chunks)
            if expected is None:
                continue
            # The windows themselves must be exact: edit_pairs' whole-file safety net
            # would otherwise hide a windowing bug behind a passing test.
            windows, codex_result = patch.window_pairs(original, chunks)
            assert codex_result == expected
            assert patch.apply_pairs(original, windows) == expected, (original, body)
            assert _resolve(tmp_path, original, chunks) == expected, (original, body)
            checked += 1
        assert checked > 200  # the property was actually exercised


class TestResponse:
    def test_reads_codex_success_listing(self):
        response = (
            "Exit code: 0\nWall time: 0.1 seconds\nOutput:\n"
            "Success. Updated the following files:\nA b.txt\nD old.txt\n"
        )
        assert patch.changed_paths_from_response(response) == [("A", "b.txt"), ("D", "old.txt")]

    def test_anything_else_is_empty(self):
        assert patch.changed_paths_from_response("error: boom") == []
        assert patch.changed_paths_from_response({"stdout": "x"}) == []
