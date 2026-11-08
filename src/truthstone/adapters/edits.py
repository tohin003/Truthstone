"""What an edit adds, line by line, as each host spells an edit (rule D, ``intent/dead_switch.py``).

The hosts' tool and argument names stay here, outside the core (``tests/test_core_host_neutral.py``).
A Codex ``apply_patch`` reaches the core as one event per file; it is read whole from the event's
raw payload, so the patch's other files can supply a reader. A file tool's ``Write``, ``Edit`` or
``MultiEdit`` is read from its arguments; a ``Write`` adds only the lines the file did not have. Ported
unchanged from the frozen ``premise_proto_d4.py`` (``_added_lines_of_event``, ``_rel``, and the file its
``install()`` limits the places to).
"""

from __future__ import annotations

from pathlib import Path


def added_lines(event, root: Path) -> list[tuple[str, list[str]]]:
    """(rel, added lines) for every file of the edit: a Codex patch's every file (from the raw payload),
    or the file tool's one file."""
    out: list[tuple[str, list[str]]] = []
    raw = event.raw or {}
    tool_input = raw.get("tool_input")
    if raw.get("tool_name") == "apply_patch":
        from truthstone.adapters.codex import patch as patchlib

        text = tool_input.get("command") if isinstance(tool_input, dict) else tool_input
        try:
            ops = patchlib.parse_patch(text)
        except Exception:  # noqa: BLE001 - a patch that does not parse is silence
            return []
        cwd = Path(str(raw.get("cwd") or root))
        for op in ops:
            rel = relative(root, cwd, op.path)
            if rel is None:
                continue
            if op.kind == "add":
                out.append((rel, (op.contents or "").splitlines()))
            elif op.kind == "update":
                added = []
                for chunk in op.chunks:
                    old = set(chunk.old_lines)
                    added += [line for line in chunk.new_lines if line not in old]
                out.append((rel, added))
        return out
    args = event.arguments or {}
    path = args.get("file_path")
    if not isinstance(path, str):
        return []
    rel = relative(root, Path(str(event.workspace or root)), path)
    if rel is None:
        return []
    if event.tool == "Write":
        # Only the lines the file did not have: a Write rewrites the whole file.
        try:
            full = root / rel
            text = full.read_text(encoding="utf-8", errors="ignore") if full.is_file() else ""
            had = set(text.splitlines())
        except OSError:
            had = set()
        out.append((rel, [line for line in str(args.get("content") or "").splitlines() if line not in had]))
    elif event.tool == "Edit":
        old = set(str(args.get("old_string") or "").splitlines())
        new = str(args.get("new_string") or "").splitlines()
        out.append((rel, [line for line in new if line not in old]))
    elif event.tool == "MultiEdit":
        added = []
        for e in args.get("edits") or []:
            old = set(str(e.get("old_string") or "").splitlines())
            added += [line for line in str(e.get("new_string") or "").splitlines() if line not in old]
        out.append((rel, added))
    return out


def edited_file(event, root: Path) -> str | None:
    """The repository-relative file this event edits (the prototype's ``this_file``), or None."""
    raw = str((event.arguments or {}).get("file_path") or "")
    return relative(root, Path(str(event.workspace or root)), raw)


def relative(root: Path, cwd: Path, raw: str) -> str | None:
    try:
        p = Path(raw).expanduser()
        p = p if p.is_absolute() else cwd / p
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None
