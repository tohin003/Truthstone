"""Codex ``apply_patch`` envelopes: parse them, and work out exactly what they would do.

Codex edits files with one tool, ``apply_patch``, whose hook input is the raw patch text
(``tool_input.command``, verified against captured payloads). Truthstone's core thinks in
Claude Code's vocabulary — ``Write``, ``Edit``, ``MultiEdit`` — so the adapter has to turn
one patch into one or more of those. That translation is only as good as its reading of
the patch, so this module is a line-for-line port of the reference implementation in
``codex-rs/apply-patch`` at ``rust-v0.166.0``:

* ``parser.rs`` / ``streaming_parser.rs`` — the grammar, including its leniencies (a
  ``<<'EOF'`` heredoc wrapper, whitespace around markers, ``*** Environment ID:``);
* ``file_update.rs`` / ``seek_sequence.rs`` / ``text_file.rs`` — how update hunks locate
  their lines (exact, then ignoring trailing whitespace, then both ends, then Unicode
  punctuation) and how the result is rebuilt (line endings preserved, inserted lines use
  the file's first ending, every line terminated).

Nothing here touches the filesystem. Callers read the file (inside the workspace) and hand
the text in; everything else is a pure function, which is what makes it testable against
Codex's own behaviour.

Grammar (from parser.rs)::

    start: begin_patch environment_id? hunk+ end_patch
    hunk: add_hunk | delete_hunk | update_hunk
    add_hunk: "*** Add File: " filename LF add_line+
    delete_hunk: "*** Delete File: " filename LF
    update_hunk: "*** Update File: " filename LF change_move? change?
    change_move: "*** Move to: " filename LF
    change: (change_context | change_line)+ eof_line?
    change_context: ("@@" | "@@ " /(.+)/) LF
    change_line: ("+" | "-" | " ") /(.+)/ LF
    eof_line: "*** End of File" LF
"""

from __future__ import annotations

from dataclasses import dataclass, field

BEGIN_PATCH = "*** Begin Patch"
END_PATCH = "*** End Patch"
ADD_FILE = "*** Add File: "
DELETE_FILE = "*** Delete File: "
UPDATE_FILE = "*** Update File: "
MOVE_TO = "*** Move to: "
ENVIRONMENT_ID = "*** Environment ID: "
EOF_MARKER = "*** End of File"
CHANGE_CONTEXT = "@@ "
EMPTY_CHANGE_CONTEXT = "@@"

# Generous, but bounded: a patch is model output, and this runs on the hook hot path.
MAX_PATCH_CHARS = 2_000_000


class PatchError(ValueError):
    """The text is not a patch Codex would accept. Codex rejects it before any hook runs."""


@dataclass(slots=True)
class Chunk:
    """One ``@@`` section of an update hunk (``UpdateFileChunk`` in Rust)."""

    change_context: str | None = None
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)
    # (old_index, new_index) pairs for lines written as context (" x"), so a fuzzy match
    # keeps the file's own spelling of them, exactly as Codex does.
    context_pairs: list[tuple[int, int]] = field(default_factory=list)
    is_end_of_file: bool = False

    def is_empty(self) -> bool:
        return not self.old_lines and not self.new_lines

    def push_context(self, line: str) -> None:
        self.context_pairs.append((len(self.old_lines), len(self.new_lines)))
        self.old_lines.append(line)
        self.new_lines.append(line)


@dataclass(slots=True)
class FileOp:
    """One file operation in a patch."""

    kind: str  # "add" | "delete" | "update"
    path: str  # exactly as written; absolute or relative to the tool's cwd
    contents: str = ""  # add only
    move_to: str | None = None  # update only
    chunks: list[Chunk] = field(default_factory=list)  # update only


# -- parsing ----------------------------------------------------------------------


def _lines(text: str) -> list[str]:
    """Rust ``str::lines``: split on LF, drop one trailing CR per line."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _strip_boundaries(text: str) -> list[str]:
    lines = _lines(text.strip())
    if lines and lines[0].strip() == BEGIN_PATCH and lines[-1].strip() == END_PATCH:
        return lines
    # Lenient mode: some models wrap the patch in a heredoc that never reached a shell.
    if (
        len(lines) >= 4
        and lines[0] in ("<<EOF", "<<'EOF'", '<<"EOF"')
        and lines[-1].endswith("EOF")
    ):
        inner = lines[1:-1]
        if inner and inner[0].strip() == BEGIN_PATCH and inner[-1].strip() == END_PATCH:
            return inner
    if not lines or lines[0].strip() != BEGIN_PATCH:
        raise PatchError("The first line of the patch must be '*** Begin Patch'")
    raise PatchError("The last line of the patch must be '*** End Patch'")


class _Parser:
    """Port of ``StreamingPatchParser``: one line at a time, same states, same errors."""

    def __init__(self) -> None:
        self.mode = "not_started"
        self.ops: list[FileOp] = []
        self.environment_id: str | None = None

    def _ensure_update_not_empty(self) -> None:
        if not self.ops or self.ops[-1].kind != "update":
            return
        op = self.ops[-1]
        if not op.chunks and self.mode == "update":
            raise PatchError(f"Update file hunk for path '{op.path}' is empty")
        if op.chunks and op.chunks[-1].is_empty():
            raise PatchError("Update hunk does not contain any lines")

    def _header(self, trimmed: str) -> bool:
        if self.mode == "started" and trimmed.startswith(ENVIRONMENT_ID):
            if self.environment_id is not None:
                raise PatchError("apply_patch environment_id cannot be specified more than once")
            value = trimmed[len(ENVIRONMENT_ID) :].strip()
            if not value:
                raise PatchError("apply_patch environment_id cannot be empty")
            self.environment_id = value
            return True
        if trimmed == END_PATCH:
            self._ensure_update_not_empty()
            self.mode = "ended"
            return True
        for marker, kind in ((ADD_FILE, "add"), (DELETE_FILE, "delete"), (UPDATE_FILE, "update")):
            if trimmed.startswith(marker):
                self._ensure_update_not_empty()
                self.ops.append(FileOp(kind=kind, path=trimmed[len(marker) :]))
                self.mode = kind
                return True
        return False

    def feed(self, line: str) -> None:
        trimmed = line.strip()
        mode = self.mode
        if mode == "not_started":
            if trimmed == BEGIN_PATCH:
                self.mode = "started"
                return
            raise PatchError("The first line of the patch must be '*** Begin Patch'")
        if mode in ("started", "delete"):
            if self._header(trimmed):
                return
            raise PatchError(f"'{trimmed}' is not a valid hunk header")
        if mode == "add":
            if self._header(trimmed):
                return
            if line.startswith("+"):
                self.ops[-1].contents += line[1:] + "\n"
                return
            raise PatchError(f"'{trimmed}' is not a valid hunk header")
        if mode == "update":
            self._feed_update(line)
            return
        if mode == "ended":
            if trimmed:
                raise PatchError("The last line of the patch must be '*** End Patch'")
            return
        raise PatchError(f"unexpected parser state {mode}")  # pragma: no cover

    def _feed_update(self, line: str) -> None:
        update_line = line.rstrip()
        if self._header(update_line):
            return
        op = self.ops[-1]
        chunks = op.chunks
        if chunks and chunks[-1].is_end_of_file:
            if not update_line:
                return
            if update_line != EMPTY_CHANGE_CONTEXT and not update_line.startswith(CHANGE_CONTEXT):
                raise PatchError(f"Expected update hunk to start with a @@ context marker, got: '{line}'")
        if not chunks and op.move_to is None and update_line.startswith(MOVE_TO):
            op.move_to = update_line[len(MOVE_TO) :]
            return
        is_context_marker = update_line == EMPTY_CHANGE_CONTEXT or update_line.startswith(CHANGE_CONTEXT)
        if is_context_marker and chunks and chunks[-1].is_empty():
            raise PatchError(f"Unexpected line found in update hunk: '{line}'")
        if update_line == EMPTY_CHANGE_CONTEXT:
            chunks.append(Chunk())
            return
        if update_line.startswith(CHANGE_CONTEXT):
            chunks.append(Chunk(change_context=update_line[len(CHANGE_CONTEXT) :]))
            return
        if update_line == EOF_MARKER:
            if chunks and chunks[-1].is_empty():
                raise PatchError("Update hunk does not contain any lines")
            if chunks:
                chunks[-1].is_end_of_file = True
            return
        if line == "" or line[0] in " +-":
            if not chunks:
                chunks.append(Chunk())
            chunk = chunks[-1]
            if line == "":
                chunk.push_context("")
            elif line[0] == " ":
                chunk.push_context(line[1:])
            elif line[0] == "+":
                chunk.new_lines.append(line[1:])
            else:
                chunk.old_lines.append(line[1:])
            return
        if chunks and not chunks[-1].is_empty():
            raise PatchError(f"Expected update hunk to start with a @@ context marker, got: '{line}'")
        raise PatchError(f"Unexpected line found in update hunk: '{line}'")


def parse_patch(text: str) -> list[FileOp]:
    """Parse a patch exactly as Codex 0.166.0 would. Raises :class:`PatchError`."""
    if not isinstance(text, str):
        raise PatchError("patch text must be a string")
    if len(text) > MAX_PATCH_CHARS:
        raise PatchError("patch too large to inspect")
    parser = _Parser()
    for line in _strip_boundaries(text):
        parser.feed(line)
    if parser.mode != "ended":
        raise PatchError("The last line of the patch must be '*** End Patch'")
    if not parser.ops:
        raise PatchError("patch contains no file operations")
    return parser.ops


# -- applying update hunks ----------------------------------------------------------

# seek_sequence.rs's final pass folds typographic punctuation to ASCII. Written as code
# points: the characters themselves look exactly like their ASCII targets.
_DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
_SINGLE_QUOTES = (0x2018, 0x2019, 0x201A, 0x201B)
_DOUBLE_QUOTES = (0x201C, 0x201D, 0x201E, 0x201F)
_SPACES = (0x00A0, *range(0x2002, 0x200B), 0x202F, 0x205F, 0x3000)
_PUNCT = {
    **dict.fromkeys(_DASHES, "-"),
    **dict.fromkeys(_SINGLE_QUOTES, "'"),
    **dict.fromkeys(_DOUBLE_QUOTES, '"'),
    **dict.fromkeys(_SPACES, " "),
}


def _normalise(text: str) -> str:
    return text.strip().translate(_PUNCT)


def seek_sequence(lines: list[str], pattern: list[str], start: int, eof: bool) -> int | None:
    """Port of ``seek_sequence``: four passes of decreasing strictness."""
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None
    search_start = max(len(lines) - len(pattern), start) if eof else start
    last = len(lines) - len(pattern)
    for compare in (
        lambda a, b: a == b,
        lambda a, b: a.rstrip() == b.rstrip(),
        lambda a, b: a.strip() == b.strip(),
        lambda a, b: _normalise(a) == _normalise(b),
    ):
        for i in range(search_start, last + 1):
            if all(compare(lines[i + k], pat) for k, pat in enumerate(pattern)):
                return i
    return None


@dataclass(slots=True)
class _SourceLine:
    text: str
    ending: str | None


def _parse_source(contents: str) -> tuple[list[_SourceLine], str]:
    """Port of ``SourceFile::parse``: keep each line's own ending; LF/CRLF/CR."""
    lines: list[_SourceLine] = []
    preferred: str | None = None
    start = cursor = 0
    size = len(contents)
    while cursor < size:
        char = contents[cursor]
        if char == "\r":
            ending = "\r\n" if contents.startswith("\n", cursor + 1) else "\r"
        elif char == "\n":
            ending = "\n"
        else:
            cursor += 1
            continue
        preferred = preferred or ending
        lines.append(_SourceLine(contents[start:cursor], ending))
        cursor += len(ending)
        start = cursor
    if start < size:
        lines.append(_SourceLine(contents[start:], None))
    return lines, preferred or "\n"


Replacement = tuple[int, int, list[str]]


def compute_replacements(original_lines: list[str], chunks: list[Chunk]) -> list[Replacement] | None:
    """Port of ``compute_replacements``. ``None`` where Codex would fail the patch."""
    replacements: list[Replacement] = []
    line_index = 0
    for chunk in chunks:
        if chunk.change_context is not None:
            found_ctx = seek_sequence(original_lines, [chunk.change_context], line_index, False)
            if found_ctx is None:
                return None
            line_index = found_ctx + 1

        if not chunk.old_lines:
            replacements.append((len(original_lines), 0, list(chunk.new_lines)))
            continue

        pattern = chunk.old_lines
        new_slice = chunk.new_lines
        found = seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)
        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)
        if found is None:
            return None

        old_start = new_start = 0
        for old_ctx, new_ctx in chunk.context_pairs:
            if old_ctx >= len(pattern) or new_ctx >= len(new_slice):
                break
            if old_start != old_ctx or new_start != new_ctx:
                replacements.append(
                    (found + old_start, old_ctx - old_start, list(new_slice[new_start:new_ctx]))
                )
            old_start = old_ctx + 1
            new_start = new_ctx + 1
        if old_start != len(pattern) or new_start != len(new_slice):
            replacements.append((found + old_start, len(pattern) - old_start, list(new_slice[new_start:])))
        line_index = found + len(pattern)

    replacements.sort(key=lambda item: item[0])
    return replacements


def _render(lines: list[_SourceLine], replacements: list[Replacement], preferred: str) -> str:
    """Port of ``apply_replacements`` + ``into_contents``."""
    out: list[_SourceLine] = []
    index = 0
    for start, old_len, new_segment in replacements:
        out.extend(lines[index:start])
        out.extend(_SourceLine(text, preferred) for text in new_segment)
        index = start + old_len
    out.extend(lines[index:])
    return "".join(line.text + (line.ending or preferred) for line in out)


def apply_chunks(original: str, chunks: list[Chunk]) -> str | None:
    """The file content Codex would produce, or ``None`` if Codex would reject the hunk."""
    lines, preferred = _parse_source(original)
    replacements = compute_replacements([line.text for line in lines], chunks)
    if replacements is None:
        return None
    return _render(lines, replacements, preferred)


# -- expressing an update in the core's vocabulary ---------------------------------


def edit_pairs(original: str, chunks: list[Chunk]) -> list[tuple[str, str]] | None:
    """(old_string, new_string) pairs that reproduce Codex's result *exactly*.

    The core's evidence engine applies an ``Edit`` as ``before.replace(old, new, 1)`` and a
    ``MultiEdit`` as a sequence of those. A hunk's raw lines are not good enough for that:
    fuzzy matching, context lines, pure insertions and repeated text all make a naive
    ``old in before`` either fail or hit the wrong occurrence — and a wrong post-edit file
    means wrong evidence. So each pair here is a window of the *original* text:

    * anchored to whole lines, with pure insertions widened to a neighbouring line;
    * widened upwards until its first occurrence is its own position, so ``replace(…, 1)``
      lands where Codex lands;
    * merged with the window above when widening makes them touch;
    * emitted bottom-up, so applying one never moves the text of the next.

    Returns ``None`` when Codex itself would reject the hunks.
    """
    computed = window_pairs(original, chunks)
    if computed is None:
        return None
    pairs, expected = computed
    # Belt and braces: never hand the core a rewrite that does not reproduce Codex.
    return pairs if apply_pairs(original, pairs) == expected else [(original, expected)]


def apply_pairs(original: str, pairs: list[tuple[str, str]]) -> str:
    """Apply pairs exactly as ``evidence.extractors.resolve_edit`` does."""
    text = original
    for old, new in pairs:
        text = text.replace(old, new, 1) if old else text + new
    return text


def window_pairs(original: str, chunks: list[Chunk]) -> tuple[list[tuple[str, str]], str] | None:
    """The windowed pairs and Codex's expected result, before any safety fallback."""
    lines, preferred = _parse_source(original)
    texts = [line.text for line in lines]
    replacements = compute_replacements(texts, chunks)
    if replacements is None:
        return None
    expected = _render(lines, replacements, preferred)
    if not replacements:
        return [], expected
    # An unterminated last line gains an ending wherever it ends up; only a whole-file
    # window reproduces that byte-for-byte, and an empty file has no line to anchor to.
    if not lines or lines[-1].ending is None:
        return [(original, expected)], expected

    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.text) + len(line.ending or ""))

    windows: list[list] = []  # [start, end, [replacements]]
    for start, old_len, segment in replacements:
        w_start, w_end = start, start + old_len
        if old_len == 0:  # a pure insertion has no text of its own to find
            if start > 0:
                w_start = start - 1
            else:
                w_end = min(start + 1, len(lines))
        window = [w_start, w_end, [(start, old_len, segment)]]
        while True:
            if windows and window[0] < windows[-1][1]:
                previous = windows.pop()
                window = [previous[0], max(previous[1], window[1]), previous[2] + window[2]]
                continue
            old_text = original[offsets[window[0]] : offsets[window[1]]]
            if original.find(old_text) == offsets[window[0]]:
                break
            window[0] -= 1  # find() located an earlier copy; take one more line of context
        windows.append(window)

    pairs: list[tuple[str, str]] = []
    for w_start, w_end, reps in reversed(windows):
        old_text = original[offsets[w_start] : offsets[w_end]]
        parts: list[str] = []
        cursor = w_start
        for start, old_len, segment in sorted(reps, key=lambda item: item[0]):
            parts.extend(lines[i].text + (lines[i].ending or preferred) for i in range(cursor, start))
            parts.extend(text + preferred for text in segment)
            cursor = start + old_len
        parts.extend(lines[i].text + (lines[i].ending or preferred) for i in range(cursor, w_end))
        pairs.append((old_text, "".join(parts)))
    return pairs, expected


# -- reading Codex's verdict --------------------------------------------------------


def changed_paths_from_response(response: object) -> list[tuple[str, str]]:
    """``[("A"|"M"|"D", path), ...]`` from a successful ``apply_patch`` result.

    Captured shape: ``"Exit code: 0\\n...Output:\\nSuccess. Updated the following
    files:\\nA b.txt\\nD old.txt\\n"``. A move is reported only as ``M <destination>``, so
    callers must still use the patch to learn the source path.
    """
    if not isinstance(response, str) or "Success." not in response:
        return []
    out: list[tuple[str, str]] = []
    after = response.split("Updated the following files:", 1)
    if len(after) != 2:
        return []
    for raw in after[1].splitlines():
        line = raw.strip()
        if len(line) > 2 and line[0] in "AMD" and line[1] == " ":
            out.append((line[0], line[2:].strip()))
    return out
