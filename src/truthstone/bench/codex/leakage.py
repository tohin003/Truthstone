"""The no-leakage lint's list (ARCHITECTURE-v0.2 §6.2 rule 4): what would identify a golden task.

Product code must never be keyed to a benchmark task. ``tests/test_no_dev_leakage.py`` scans
``src/`` and the non-bench ``tests/`` for every golden task id and for strings unique to one task:
identifiers and invented names that appear in a task's own files (its prompts, overlay, hidden
tests and solutions) but in no base repository, no other golden task and no English word list.
The list is stored only as SHA-256 hashes of the lower-cased strings
(``tests/fixtures/golden/leakage.json``): the lint can match them, and nobody can read them as a
hint list. The benchmark builder regenerates it whenever a task changes
(``python -m truthstone.bench.codex leakage --write``).
"""

from __future__ import annotations

import builtins
import hashlib
import json
import keyword
import re
import sys
from pathlib import Path

from truthstone.bench.codex import suite

GOLDEN_SUITES = (
    "golden-dev",
    "golden-heldout",
    "golden-heldout2",
    "golden-heldout3",
    "golden-rehearsal",
    "golden-heldout4",
    "golden-heldout5",
    "golden-heldout6",
    "golden-candidates",
    "golden-dev-keeptests",  # G40: a dev split, never frozen; its strings are task material too
    "golden-probe1",  # G42: a probe split, never frozen; its strings are task material too
    "golden-probe2",  # G45: a second probe split, never frozen; its strings are task material too
    "golden-probe3",  # G47: a third probe split, never frozen; its strings are task material too
    "golden-probe4",  # G48: a fourth probe split, never frozen; its strings are task material too
    "golden-probe5",  # G50: a fifth probe split, never frozen; its strings are task material too
)
LIST_PATH = suite.GOLDEN_ROOT / "leakage.json"
WORDS = Path("/usr/share/dict/words")
MIN_LENGTH = 7
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".mts",
    ".js",
    ".json",
    ".toml",
    ".md",
    ".txt",
    ".csv",
    ".cfg",
    ".ini",
    ".yml",
    ".yaml",
    ".sh",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.lower().encode("utf-8")).hexdigest()


def identifiers(text: str) -> set[str]:
    """Identifiers and their dotted parts, as a scanner would see them."""
    found: set[str] = set()
    for match in _IDENT.finditer(text):
        dotted = match.group(0)
        found.add(dotted)
        found.update(dotted.split("."))
    return found


def _files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in _TEXT_SUFFIXES and "node_modules" not in p.parts
    ]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _english() -> set[str]:
    try:
        return {w.strip().lower() for w in WORDS.read_text(encoding="utf-8", errors="replace").splitlines()}
    except OSError:
        return set()


def _generic() -> set[str]:
    """Python's own vocabulary: keywords, builtins, stdlib modules and the names on the objects
    any program uses (str and path methods, json, shutil...)."""
    import collections
    import datetime
    import os
    import pathlib
    import shutil
    import subprocess
    import tomllib

    names = set(keyword.kwlist) | set(dir(builtins)) | set(sys.stdlib_module_names)
    common = (str, bytes, list, dict, set, int, float, pathlib.Path, os, os.path, shutil, json, re)
    common += (subprocess, sys, tomllib, collections, datetime, datetime.date, datetime.datetime)
    for obj in common:
        names |= set(dir(obj))
    return {n.lower() for n in names} | _stdlib_identifiers()


def _stdlib_identifiers() -> set[str]:
    """Every identifier in the standard library's own source: general code, never a task's."""
    import sysconfig

    found: set[str] = set()
    for path in Path(sysconfig.get_paths()["stdlib"]).rglob("*.py"):
        if "test" in path.parts or "site-packages" in path.parts:
            continue
        found |= {t.lower() for t in _IDENT.findall(_read(path)) if "." not in t}
    return found


def product_identifiers() -> set[str]:
    """Identifiers in the product's code and tests today (the lint's scanned tree). Reviewed by
    the benchmark builder when the list is rebuilt: an overlap is generic vocabulary, or a leak
    to report, never silently kept."""
    root = suite.REPO_ROOT
    excluded = (root / "src" / "truthstone" / "bench", root / "tests" / "bench", root / "tests" / "fixtures")
    found: set[str] = set()
    for top in (root / "src", root / "tests"):
        for path in _files(top):
            if not any(ex in path.parents for ex in excluded):
                found |= {s.lower() for s in identifiers(_read(path))}
    return found


_SUFFIXES = (
    ("ies", "y"), ("ied", "y"), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("es", ""),
    ("s", ""), ("ly", ""), ("er", ""), ("ers", ""), ("ness", ""), ("ment", ""), ("ments", ""),
    ("ised", "ize"), ("ises", "ize"), ("ising", "ize"), ("ise", "ize"), ("isation", "ization"),
    ("able", ""), ("able", "e"), ("ally", "al"),
)  # fmt: skip
# Generic technical words a dictionary misses; never identify a task.
STOPWORDS = frozenset(
    {
        "cpython", "localhost", "pytest", "stdout", "stderr", "stdin", "subprocess", "tempfile",
        "dataclass", "dataclasses", "typescript", "javascript", "readme", "changelog", "unittest",
        "monkeypatch", "tmp_path", "capsys", "fixture", "fixtures", "parametrize", "codebase",
        "username", "filename", "filenames", "pathname", "timestamp", "timestamps", "metadata",
        "boolean", "booleans", "workflow", "workflows", "config", "configs", "toolchain", "runtime",
        "standalone", "gitignore", "gitignored", "keyword", "keywords",
        # Reviewed 2026-11-04 when the list was first built: in a golden task and already in the
        # product's code or tests, and generic. Extending this set is a reviewed decision, never a
        # way to quiet the lint: a new overlap is a leak until shown otherwise.
        "as_json", "conftest", "deterministically", "git_author_email", "git_author_name",
        "git_committer_email", "git_committer_name", "git_config_nosystem", "htmlcov", "nexport",
        "node_modules", "ruff_cache", "test_pagination", "top_level", "tsconfig", "unparseable",
        "workspace",  # reviewed 2026-11-04 (G8): a generic word, also in product code
        "pytest_cache",  # reviewed 2026-11-04 (G11): a tool's cache directory, in core's ignore list
        # Reviewed 2026-11-04 (WP0, merging the core fixes): generic, and written on a branch
        # that never held the golden set. max_bytes: log rotation and scan limits; subcommand:
        # shell-command parsing; nversion: "\nversion" in a pyproject literal, as nexport.
        "max_bytes", "nversion", "subcommand",
        # Reviewed 2026-11-06 (G28, building golden-heldout3, which postdates the product code):
        # generic, in a new task and already in the product's code or tests. A JSON Schema
        # keyword, a pytest fixture flag and an English word; every other overlap was renamed in
        # its task instead.
        "additionalproperties", "autouse", "lifecycle",
        # Reviewed 2026-11-06 (day 3): external names a detector must match as written.
        "ds_store",  # an operating-system metadata file name
        "toequal", "tothrowerror",  # test-framework assertion APIs
        # Reviewed 2026-11-08 (G38, building golden-rehearsal, which postdates the product code):
        # generic, in a new task and already in the product's code or tests. A test-framework hook,
        # a test-outcome word, two common test module names, a working-directory word and an
        # English word; the one task-specific overlap (a function name) was renamed in its task.
        "aftereach", "xfailed", "test_db", "test_money", "workdir", "spreadsheet",
        # Reviewed 2026-11-08 (round-4 settlement S29, merging golden-rehearsal onto the product
        # commit 308f021 for its launch branch): an external API name a product detector, written on
        # a branch that never held the rehearsal, must match as written (as the day-3 names above).
        "execsync",
        # Reviewed 2026-11-08 (G39, building golden-heldout4): external names new tasks use as
        # written and the product's code or tests already hold: two pytest APIs and a JavaScript
        # platform global. Every other overlap was renamed in its task.
        "at_level", "importorskip", "structuredclone",
        # Reviewed 2026-11-12 (G42, freezing golden-probe1, built blind after the product code):
        # generic, in a new task and already in the product's code or tests. Three English words
        # (two British spellings and a compound noun), a common package-script name, and a dunder
        # after a newline escape in a Python string literal (as nexport and nversion above).
        "colours", "honoured", "marketplace", "typecheck", "n__all__",
        # Reviewed 2026-11-13 (G45, freezing golden-probe2, built blind after the product code):
        # generic, in a new task and already in the product's code or tests. Three common snake_case
        # names for a batch, a page and a retry count, a British spelling, and a common test module
        # name and test function name; the two task-specific overlaps were renamed in their tasks.
        "batch_size", "page_size", "max_retries", "honouring", "test_retries", "test_defaults",
        # Reviewed 2026-11-13 (G47, freezing golden-probe3, built blind after the product code):
        # generic, in a new task and already in the product's code or tests. A standard-library
        # exception name (sqlite3's, defined in C, so no stdlib source spells it); the one
        # task-specific overlap (a hidden test's function name) was renamed in its task.
        "operationalerror",
        # Reviewed 2026-11-13 (G48, freezing golden-probe4, built blind after the product code):
        # generic, in a new task and already in the product's code or tests. A common package-script
        # name (as typecheck above); the two task-specific overlaps (a hidden test's helper name and a
        # generated module's constant) were renamed in their tasks.
        "codegen",
        # Reviewed 2026-11-13 (G49, building golden-heldout5): generic names new tasks use as
        # written and the product's code or tests already hold: an English word the word list
        # lacks, a test-framework assertion API, an npm script name, a test-module name and the
        # usual HTTP-client retry option. Every other overlap was renamed in its task.
        # (spreadsheet, typecheck, test_db, max_retries: listed above too.)
        "tocontain",
        # Reviewed 2026-11-13 (G51, building golden-heldout6): generic names new tasks use as
        # written and the product's code or tests already hold: two English words the word list
        # lacks, a standard command-line option, a widely used environment-variable convention and
        # a common HTTP field name. Every other overlap was renamed in its task.
        # (colours, marketplace: listed above too.)
        "maxdepth", "clicolor_force", "request_id",
    }
)  # fmt: skip


def _englishish(word: str, words: set[str]) -> bool:
    w = word.lower()
    if w in words:
        return True
    for suffix, stem in _SUFFIXES:
        if not w.endswith(suffix):
            continue
        root = w[: -len(suffix)]
        if root + stem in words:
            return True
        if len(root) > 2 and root[-1] == root[-2] and root[:-1] in words:  # trimmed, planned
            return True
    return False


def _code_like(token: str) -> bool:
    """A name only code would carry: snake_case, camelCase, or letters mixed with digits."""
    bare = token.strip("_")
    return (
        "_" in bare
        or "." in bare
        or bool(re.search(r"[a-z][A-Z]", token))
        or (bool(re.search(r"[0-9]", bare)) and bool(re.search(r"[A-Za-z]{2}", bare)))
    )


def unique_strings() -> dict[str, set[str]]:
    """Per task: the strings that would identify it (see the module docstring). Two kinds:
    code-like names (snake_case, camelCase, dotted, letters with digits) and invented words (no
    dictionary entry, inflections included), each found in exactly one golden task's own files
    and in no base repository."""
    tasks = [t for name in GOLDEN_SUITES for t in suite.load_suite(suite=name)]
    base_tokens: set[str] = set()
    for base in sorted({t.base_root for t in tasks}):
        for path in _files(base):
            base_tokens |= {s.lower() for s in identifiers(_read(path))}
    per_task: dict[str, set[str]] = {}
    for task in tasks:
        text = "\n".join(task.prompt(p) for p in suite.PHRASINGS)
        text += "\n".join(_read(p) for p in _files(task.root) if p.name != "task.toml")
        per_task[task.id] = identifiers(text)
    counts: dict[str, int] = {}
    for tokens in per_task.values():
        for token in {t.lower() for t in tokens}:
            counts[token] = counts.get(token, 0) + 1
    words, generic = _english(), _generic() | STOPWORDS
    out: dict[str, set[str]] = {}
    for task_id, tokens in per_task.items():
        keep = set()
        for token in tokens:
            low = token.lower()
            if len(low) < MIN_LENGTH or counts[low] != 1 or low in base_tokens or low in generic:
                continue
            if "." in token or sum(c.isalpha() for c in token) < 3:
                continue  # obj.method idioms and numerals; a task-unique part is kept on its own
            if _code_like(token) or (token.isalpha() and not _englishish(token, words)):
                keep.add(low)
        out[task_id] = keep
    return out


def build() -> dict[str, object]:
    tasks = [t for name in GOLDEN_SUITES for t in suite.load_suite(suite=name)]
    strings = unique_strings()
    overlap = sorted({s for found in strings.values() for s in found} & product_identifiers())
    return {
        "_overlap_with_product_code": overlap,  # what the lint will flag; printed, never stored
        "about": "SHA-256 of lower-cased golden task ids and task-unique strings; see bench/codex/leakage.py",
        "ids": sorted(digest(t.id) for t in tasks),
        "strings": sorted({digest(s) for found in strings.values() for s in found}),
    }


def write(path: Path = LIST_PATH) -> dict[str, object]:
    data = build()
    stored = {k: v for k, v in data.items() if not k.startswith("_")}
    path.write_text(json.dumps(stored, indent=1) + "\n", encoding="utf-8")
    return data
