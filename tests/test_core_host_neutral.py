"""H4 — the core does not learn any more of Claude Code's vocabulary.

The core still speaks some of Claude Code's tool, argument and hook-field names
(``IMPROVEMENTS.md`` §4.4); that is debt with a migration plan (H6). This test stops it
growing. It parses every module under ``src/agentguard`` except ``adapters/`` and finds
each **string literal** (docstrings excluded) whose whole value is one of the names below.
Every occurrence that exists today is recorded in ``ALLOWED``. A new one fails, naming
the module and the literal; translate it in the adapter instead, or use the core's own
vocabulary (``docs/ADAPTER-CONTRACT.md``). The allowlist only shrinks: when an occurrence
goes away, lower its count.

Scope, deliberately narrow: identifiers, comments and docstrings are not scanned. A
literal is what makes code *depend* on a host's spelling.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

TOOL_NAMES = frozenset({"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "PowerShell"})
ARGUMENT_NAMES = frozenset(
    {"file_path", "notebook_path", "old_string", "new_string", "replace_all", "new_source"}
)
HOOK_FIELDS = frozenset(
    {
        "tool_response",
        "hook_event_name",
        "stop_hook_active",
        "permissionDecision",
        "updatedInput",
        "background_tasks",
        "PostToolUseFailure",
    }
)
VOCABULARY = TOOL_NAMES | ARGUMENT_NAMES | HOOK_FIELDS

# Every occurrence as of e087bf5 plus H4 (which removed the daemon's last one). Other work
# in flight edits these modules; the lead reconciles this table when it lands.
ALLOWED: dict[tuple[str, str], int] = {
    ("agentguard.bench.mutation", "Write"): 1,
    ("agentguard.bench.mutation", "file_path"): 1,
    ("agentguard.core.engine", "file_path"): 2,
    ("agentguard.core.engine", "notebook_path"): 2,
    ("agentguard.core.engine", "stop_hook_active"): 1,
    # SHELL_TOOLS (G1-core): the one place the core names host shell tools, so the
    # engine no longer does. Goes when canonical actions (H6) replace tool names.
    ("agentguard.core.events", "Bash"): 1,
    ("agentguard.core.events", "PowerShell"): 1,
    ("agentguard.core.events", "Edit"): 1,
    ("agentguard.core.events", "MultiEdit"): 1,
    ("agentguard.core.events", "NotebookEdit"): 1,
    ("agentguard.core.events", "Write"): 1,
    ("agentguard.evidence.engine", "file_path"): 1,
    ("agentguard.evidence.engine", "notebook_path"): 1,
    ("agentguard.evidence.extractors", "Bash"): 1,
    ("agentguard.evidence.extractors", "Edit"): 1,
    ("agentguard.evidence.extractors", "MultiEdit"): 1,
    ("agentguard.evidence.extractors", "NotebookEdit"): 1,
    ("agentguard.evidence.extractors", "Write"): 1,
    ("agentguard.evidence.extractors", "file_path"): 1,
    ("agentguard.evidence.extractors", "new_source"): 1,
    ("agentguard.evidence.extractors", "new_string"): 2,
    ("agentguard.evidence.extractors", "notebook_path"): 1,
    ("agentguard.evidence.extractors", "old_string"): 2,
    ("agentguard.evidence.extractors", "replace_all"): 2,
    # 2: risky_command and A4's read-only-Bash classifier. Bash stays the core's shell
    # vocabulary until canonical actions (H6) replace it.
    ("agentguard.validate.checks", "Bash"): 2,
    ("agentguard.validate.checks", "Edit"): 1,
    ("agentguard.validate.checks", "MultiEdit"): 1,
    ("agentguard.validate.checks", "Write"): 2,
    ("agentguard.validate.modify", "Bash"): 1,
    # A10: dependency advice depends on whether the installer was a shell command.
    ("agentguard.validate.validator", "Bash"): 1,
    ("agentguard.validate.validator", "file_path"): 1,
    ("agentguard.validate.validator", "notebook_path"): 1,
}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def scan(src: Path = SRC) -> Counter[tuple[str, str]]:
    """``(module, literal) -> count`` for every vocabulary literal outside ``adapters/``."""
    counts: Counter[tuple[str, str]] = Counter()
    for path in sorted((src / "agentguard").rglob("*.py")):
        rel = path.relative_to(src)
        if rel.parts[1] == "adapters":
            continue
        module = ".".join(rel.with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in VOCABULARY
                and id(node) not in docstrings
            ):
                counts[(module, node.value)] += 1
    return counts


def test_no_new_host_vocabulary_in_the_core():
    found = scan()
    new = sorted((key, n, ALLOWED.get(key, 0)) for key, n in found.items() if n > ALLOWED.get(key, 0))
    lines = [
        f"  {module}: {literal!r} appears {n} time(s), {allowed} allowed"
        for (module, literal), n, allowed in new
    ]
    header = "Claude Code vocabulary added to the core (translate it in the adapter):\n"
    assert not new, header + "\n".join(lines)


def test_the_allowlist_only_shrinks():
    found = scan()
    stale = sorted(
        (key, allowed, found.get(key, 0)) for key, allowed in ALLOWED.items() if found.get(key, 0) < allowed
    )
    lines = [f"  {module}: {literal!r} allowed {allowed}, now {n}" for (module, literal), allowed, n in stale]
    assert not stale, "occurrences removed; lower ALLOWED so they cannot come back:\n" + "\n".join(lines)


def test_new_host_neutral_modules_stay_clean():
    found = scan()
    for module in ("agentguard.core.hosts", "agentguard.daemon.app"):
        assert not [key for key in found if key[0] == module], module


def test_the_scan_sees_what_it_should_and_skips_docstrings(tmp_path):
    """The lint must not be vacuous, and must not flag prose."""
    package = tmp_path / "agentguard" / "core"
    package.mkdir(parents=True)
    (tmp_path / "agentguard" / "adapters").mkdir()
    (package / "probe.py").write_text(
        '"""Mentions "Bash" and file_path in prose."""\n'
        'def f(event):\n'
        '    """And here: Edit."""\n'
        '    return event.tool == "Bash" and event.arguments.get("file_path") and f"Bash {event}"\n'
    )
    (tmp_path / "agentguard" / "adapters" / "host.py").write_text('TOOL = "Bash"\n')
    expected = {("agentguard.core.probe", "Bash"): 1, ("agentguard.core.probe", "file_path"): 1}
    assert scan(tmp_path) == Counter(expected)
