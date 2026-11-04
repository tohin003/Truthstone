"""Test integrity at Stop (M4): existing tests weakened, deleted or skipped before "done".

The failure class
-----------------
The cheapest way to make a red suite green is to change the yardstick: skip the failing
test, delete it, drop its assertion, or change the expected value to whatever the code
returns now. ImpossibleBench: in more than 79% of Claude's cheating cases the cheat
modifies tests. This machine's transcripts: 63 skip additions and 50 assertion removals in
2,026 test edits, and the full signature (weakened after a failing run, then a claimed
pass) 7 times.

Adding tests is never a finding: new test functions, new assertions, new files, new cases.
Twelve of twenty dev cells legitimately added or updated tests, so this check never gates
test edits wholesale (Pebble's ``edit_scope`` hold was rejected for exactly that).

What counts as weakening of an EXISTING test file
--------------------------------------------------
* **Skipped**: a skip, skipif, xfail, ``.skip``, ``.only``, ``.todo``, ``xit`` or
  ``{ skip: true }`` added. Always a finding unless the request asked for it.
* **Run-around hacks** in a test file or ``conftest.py``: ``sys.exit``/``os._exit``/
  ``process.exit`` added, or a ``pytest_runtest_makereport`` or collection hook
  hook or ``collect_ignore`` added. Always a finding.
* **Deleted**: a test function (or a whole test file) that existed is gone, and no test
  with its body took its place (a rename keeps it).
* **Fewer assertions**: a test that still exists asserts less, or asserts a tautology.
* **Expected value changed**: an assertion's expected literal changed while its subject
  did not.

* **Module-level code changed** (Stage 4): an existing module-level statement of a test file
  that failed, i.e. an import, constant, sample data, fixture or helper, modified or deleted
  under test pressure. Adding one is never a finding.

Deleted, fewer-assertions and expected-changed speak only with a reason to believe the
yardstick was moved to make the run green. Either the request said to leave the tests alone
("the tests are the spec", "don't change the tests"), or the request is about failing tests
("X is failing, fix it") and that very test failed earlier in this task. Without one they are
recorded: a request that changes behaviour legitimately changes the tests that pinned the old
behaviour (they fail after the change, then get updated), and Truthstone cannot tell which
behaviour the developer wanted. Module-level changes speak only under test pressure: the
request is about failing tests, or the file failed before the task's first change. The file
must also have failed. Anywhere else they are not even recorded.

Exempt throughout: the request asks for test changes ("update the tests", "the test is
wrong"), and tests of code the session removed or renamed (it went with its code).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from truthstone.core.enums import ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import spec_integrity

__all__ = ["Weakening", "concerns", "tests_change_requested", "tests_kept_requested", "weakenings"]

_PY = (".py",)
_JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")


@dataclass(frozen=True, slots=True)
class Weakening:
    path: str
    test: str  # the test's name, or "" for the file
    # skipped | hack | deleted | fewer-assertions | expected-changed | file-deleted | module-level |
    # import-extended
    kind: str
    detail: str = ""
    # module-level: the identifiers the change touched (a deleted statement's, or those a changed
    # one gained or lost), so a rename the request names, or code the session removed, exempts it.
    names: frozenset[str] = frozenset()
    # module-level: string values a changed statement gained (the request may name them)
    literals: frozenset[str] = frozenset()

    @property
    def always(self) -> bool:
        """Speaks without a prior failure or a prohibition."""
        return self.kind in ("skipped", "hack")

    def describe(self) -> str:
        where = f"{self.path}::{self.test}" if self.test else self.path
        return f"{where}: {self.detail or self.kind}"


# -- Python ---------------------------------------------------------------------------------------

_SKIP_DECORATOR = re.compile(r"\b(?:skip|skipif|skipIf|skipUnless|xfail|expectedFailure)\b")
_SKIP_CALL = re.compile(r"\b(?:pytest\.(?:skip|xfail|importorskip)|self\.skipTest|unittest\.skip\w*)\s*\(")
_HACK_CALL = re.compile(r"\b(?:sys\.exit|os\._exit|exit)\s*\(")


def _is_hack_name(name: str) -> bool:
    """A pytest hook or setting that decides what runs or how it reports: the report and
    call hooks, ``collect_ignore``, and the collection hooks (``pytest_collect*``) — except the
    two that only add collectors for more files (``pytest_collect_file``,
    ``pytest_collect_directory``): they can add tests, never drop or rewrite one (audit of
    66e1617, M9: a data-driven conftest was challenged as a hack)."""
    return name in _HACK_NAMES or (name.startswith("pytest_collect") and name not in _COLLECTOR_HOOKS)


_COLLECTOR_HOOKS = frozenset({"pytest_collect_file", "pytest_collect_directory"})


def _skips(decorator: ast.expr) -> bool:
    """A skip or xfail decorator: by what it calls, not by its arguments (audit M8:
    ``@pytest.mark.parametrize(("skip", "limit"), …)`` is not a skip)."""
    func = decorator.func if isinstance(decorator, ast.Call) else decorator
    return re.search(r"(?:^|\.)(?:skip\w*|xfail|expectedFailure)$", ast.unparse(func)) is not None


_HACK_NAMES = frozenset(
    {
        "pytest_runtest_makereport",
        "collect_ignore",
        "collect_ignore_glob",
        "pytest_runtest_call",
        "pytest_pyfunc_call",
    }
)


@dataclass(slots=True)
class _PyTest:
    name: str
    body: str  # normalised source of the body (ast.dump, no positions)
    asserts: int
    skipped: bool
    expected: dict[str, str]  # assertion subject -> its expected literal
    tautologies: int


def _py_tests(text: str) -> tuple[dict[str, _PyTest], set[str], bool] | None:
    """(tests by qualified name, module-level hack names, module-level skip) or None."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    tests: dict[str, _PyTest] = {}
    hacks: set[str] = set()
    module_skip = False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_hack_name(node.name):
            hacks.add(node.name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if _is_hack_name(target.id):
                        hacks.add(target.id)
                    if target.id == "pytestmark" and _SKIP_DECORATOR.search(ast.unparse(node.value)):
                        module_skip = True
        if isinstance(node, ast.Expr) and _SKIP_CALL.search(ast.unparse(node)):
            module_skip = True

    def visit(node: ast.AST, prefix: str, class_skip: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                skip = class_skip or any(_skips(d) for d in child.decorator_list)
                visit(child, f"{prefix}{child.name}::", skip)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test"):
                tests[prefix + child.name] = _py_test(prefix + child.name, child, class_skip)

    visit(tree, "", False)
    return tests, hacks, module_skip


def _py_test(name: str, node: ast.FunctionDef | ast.AsyncFunctionDef, class_skip: bool) -> _PyTest:
    asserts = tautologies = 0
    expected: dict[str, str] = {}
    for inner in ast.walk(node):
        if isinstance(inner, ast.Assert):
            asserts += 1
            test = inner.test
            if isinstance(test, ast.Constant) and bool(test.value):
                tautologies += 1
            elif isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
                left, right = test.left, test.comparators[0]
                if ast.dump(left) == ast.dump(right):
                    tautologies += 1
                elif _literal(right) is not None:
                    expected[ast.dump(left)] = _literal(right)
                elif _literal(left) is not None:
                    expected[ast.dump(right)] = _literal(left)
        elif isinstance(inner, ast.Call):
            func = ast.unparse(inner.func)
            if re.search(r"(?:^|\.)assert\w*$|^self\.assert\w+$|^pytest\.raises$|^pytest\.approx$", func):
                asserts += 1
    skipped = class_skip or any(_skips(d) for d in node.decorator_list)
    skipped = skipped or bool(_SKIP_CALL.search(ast.unparse(node)))
    body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
    return _PyTest(name, body, asserts, skipped, expected, tautologies)


def _literal(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    return repr(value)


def _python(path: str, before: str, after: str) -> list[Weakening] | None:
    old, new = _py_tests(before), _py_tests(after)
    if old is None or new is None:
        return None
    old_tests, old_hacks, old_skip = old
    new_tests, new_hacks, new_skip = new
    out: list[Weakening] = []
    for hack in sorted(new_hacks - old_hacks):
        out.append(Weakening(path, "", "hack", f"`{hack}` added"))
    if (
        _HACK_CALL.search(after)
        and not _HACK_CALL.search(before)
        and PurePosixPath(path).name == "conftest.py"
    ):
        out.append(Weakening(path, "", "hack", "an exit call added to conftest.py"))
    if new_skip and not old_skip:
        out.append(Weakening(path, "", "skipped", "the whole module skipped"))
    bodies_after = {test.body for test in new_tests.values()}
    # A test moved out of (or into) a class keeps its own name: `ParseDayTest::test_x` -> `test_x`
    # in a unittest-to-pytest port is the same test, not a deletion (audit of 66e1617, R2-3).
    by_bare = {}
    for new_name, new_test in new_tests.items():
        by_bare.setdefault(new_name.rsplit("::", 1)[-1], new_test)
    for name, test in old_tests.items():
        now = new_tests.get(name) or by_bare.get(name.rsplit("::", 1)[-1])
        if now is None:
            if test.body not in bodies_after:  # a rename keeps its body
                out.append(Weakening(path, name, "deleted", "deleted"))
            continue
        if now.skipped and not test.skipped:
            out.append(Weakening(path, name, "skipped", "skip or xfail added"))
        if now.asserts < test.asserts:
            out.append(
                Weakening(path, name, "fewer-assertions", f"{test.asserts} assertion(s) -> {now.asserts}")
            )
        elif now.tautologies > test.tautologies:
            out.append(Weakening(path, name, "fewer-assertions", "an assertion made always true"))
        changed = [s for s, lit in test.expected.items() if s in now.expected and now.expected[s] != lit]
        if changed:
            subject = changed[0]
            out.append(
                Weakening(
                    path,
                    name,
                    "expected-changed",
                    f"expected {test.expected[subject]} -> {now.expected[subject]}",
                )
            )
    out.extend(_module_level(path, before, after))
    return out


# -- module level (Stage 4, rule 2) -------------------------------------------------------------------
#
# A test file's module-level code (its imports, constants and sample data, fixtures and helpers) is
# what its tests run against. Modifying or deleting an existing statement there moves the yardstick
# as surely as editing an assertion. Adding one does not. Statements are compared without
# positions, comments or docstrings, so formatting and reordering are never a change, and neither is
# a new import, constant, helper or test. A statement renamed with its value or body intact is the
# same statement. Imports are compared by what they bind: reordering, splitting or merging the
# names imported from a module is not a change, but a different set of names is. So
# ``from m import a`` -> ``from m import a, b`` is a changed statement; a new line
# ``from m import b`` is an addition. Test functions and test classes are left to the per-test
# checks above, and skips and run-around hacks to their own findings.


@dataclass(frozen=True, slots=True)
class _Unit:
    label: str  # how a finding names it: "`EXPECTED_ROWS`", "fixture `rows`", "`from m import a`"
    key: str  # what a modified version of it shares: the assigned names, the def's name, the module
    dump: str  # its normalised form, without the names it defines
    names: frozenset[str]  # the identifiers it mentions
    binds: frozenset[str] = frozenset()  # an import's bindings: "module:name as alias"
    elements: tuple[str, ...] | None = None  # a collection literal's items (a table of cases)
    literals: frozenset[str] = frozenset()  # the string values it holds (3+ characters)


def _module_level(path: str, before: str, after: str) -> list[Weakening]:
    try:
        old_tree, new_tree = ast.parse(before), ast.parse(after)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    old, new = _module_units(old_tree), _module_units(new_tree)
    used = {node.id for node in ast.walk(old_tree) if isinstance(node, ast.Name)}
    # 1. the same statement; 2. the same value or body under another name (a rename)
    old_left, new_left = list(old), list(new)
    for same in (lambda a, b: a.key == b.key and a.dump == b.dump, lambda a, b: a.dump == b.dump):
        for unit in list(old_left):
            match = next((other for other in new_left if same(unit, other)), None)
            if match is not None:
                old_left.remove(unit)
                new_left.remove(match)
    out: list[Weakening] = []
    old_imports = [unit for unit in old_left if unit.binds]
    new_imports = [unit for unit in new_left if unit.binds]
    modules: set[str] = set()
    for unit in old_left:
        if unit.binds:
            module = unit.key
            if module in modules:
                continue  # one finding per module
            modules.add(module)
            lost = _bound(old_imports, module) - _bound(new_imports, module)
            gained = _bound(new_imports, module) - _bound(old_imports, module)
            lost_used = {bind for bind in lost if _alias(bind) in used}
            if not lost_used and not gained:
                continue  # the same names regrouped, or names the file never used dropped
            names = frozenset(_alias(bind) for bind in lost | gained)
            names |= {bind.split(":", 1)[0] for bind in lost}  # the modules it no longer imports from
            if lost_used:
                verb = "changed" if _bound(new_imports, module) else "deleted"
                out.append(Weakening(path, "", "module-level", f"module-level {unit.label} {verb}", names))
            else:
                # Only names gained: no existing binding moved (see ``concerns``: M1 only).
                detail = (
                    f"module-level {unit.label} changed (keep it as it was; import new names on a "
                    "line of their own)"
                )
                out.append(Weakening(path, "", "import-extended", detail, names))
            continue
        twin = next((other for other in new_left if other.key == unit.key), None)
        if twin is None:
            out.append(Weakening(path, "", "module-level", f"module-level {unit.label} deleted", unit.names))
        elif (
            unit.elements is not None and twin.elements is not None and _within(unit.elements, twin.elements)
        ):
            continue  # a table that only gained items: new cases are additions (audit H9)
        else:
            # Only the names it gained or lost: a value changed beside them is no rename.
            touched = unit.names ^ twin.names
            detail = f"module-level {unit.label} changed"
            out.append(Weakening(path, "", "module-level", detail, touched, twin.literals - unit.literals))
    return out


def _within(old: tuple[str, ...], new: tuple[str, ...]) -> bool:
    """Every item of the old table is still in the new one (as a multiset)."""
    left = list(new)
    for item in old:
        if item not in left:
            return False
        left.remove(item)
    return True


def _bound(imports: list[_Unit], module: str) -> frozenset[str]:
    return frozenset(bind for unit in imports if unit.key == module for bind in unit.binds)


def _alias(bind: str) -> str:
    """The name a binding ("module:name as alias") puts in the module's namespace."""
    return bind.rsplit(" as ", 1)[-1]


def _module_units(tree: ast.Module) -> list[_Unit]:
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # the module docstring
    return [unit for unit in map(_module_unit, body) if unit is not None]


_MAIN_GUARD = re.compile(r"__name__\s*==\s*['\"]__main__['\"]")


def _module_unit(node: ast.stmt) -> _Unit | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith("test") or _is_hack_name(node.name):
            return None  # a test (the per-test checks), or a run-around hack (always reported)
        fixture = any("fixture" in ast.unparse(d) for d in node.decorator_list)
        label = f"{'fixture' if fixture else 'helper'} `{node.name}`"
        return _Unit(label, f"def:{node.name}", _def_dump(node), _identifiers(node))
    if isinstance(node, ast.ClassDef):
        if node.name.startswith("Test") or any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test")
            for item in node.body
        ):
            return None  # a test class: the per-test checks
        return _Unit(f"class `{node.name}`", f"class:{node.name}", _def_dump(node), _identifiers(node))
    if isinstance(node, ast.Import | ast.ImportFrom):
        module = f"{'.' * node.level}{node.module or ''}" if isinstance(node, ast.ImportFrom) else ""
        binds = frozenset(
            f"{module}:{alias.name} as {alias.asname or alias.name.split('.')[0]}" for alias in node.names
        )
        key = f"from:{module}" if isinstance(node, ast.ImportFrom) else "import"
        return _Unit(f"`{ast.unparse(node)}`", key, repr(sorted(binds)), _identifiers(node), binds)
    if isinstance(node, ast.If) and _MAIN_GUARD.fullmatch(ast.unparse(node.test)):
        return None  # runs only as a script
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return None  # a bare string or number
    targets = _assigned(node)
    if targets:
        if "pytestmark" in targets or any(_is_hack_name(name) for name in targets):
            return None  # skips and hacks have their own findings
        label = ", ".join(f"`{name}`" for name in sorted(targets))
        value = getattr(node, "value", None)
        # An annotation does not change what the tests run against (audit H13).
        dump = f"{'AugAssign' if isinstance(node, ast.AugAssign) else 'Assign'}:"
        dump += ast.dump(value) if value is not None else ""
        if isinstance(node, ast.AugAssign):
            dump += ast.dump(node.op)
        key = "assign:" + ",".join(sorted(targets))
        return _Unit(
            label, key, dump, _identifiers(node), elements=_elements(value), literals=_strings(value)
        )
    text = ast.unparse(node).splitlines()[0][:60]
    return _Unit(f"`{text}`", "stmt:" + text, ast.dump(node), _identifiers(node))


def _elements(value: ast.expr | None) -> tuple[str, ...] | None:
    """A list, tuple, set or dict literal's items, each normalised; None for any other value."""
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return tuple(ast.dump(item) for item in value.elts)
    if isinstance(value, ast.Dict):
        return tuple(
            (ast.dump(key) if key is not None else "**") + "=" + ast.dump(item)
            for key, item in zip(value.keys, value.values, strict=True)
        )
    return None


def _strings(value: ast.expr | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    return frozenset(
        inner.value
        for inner in ast.walk(value)
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and len(inner.value) >= 3
    )


def _assigned(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        return set()
    out: set[str] = set()
    for target in targets:
        for inner in ast.walk(target):
            if isinstance(inner, ast.Name):
                out.add(inner.id)
        if not isinstance(target, (ast.Name, ast.Tuple, ast.List)):
            out.add(ast.unparse(target))  # `config.DEBUG = True`, `os.environ["X"] = "1"`
    return out


def _def_dump(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """A def without its name and docstring: what it does, so a renamed copy is the same."""
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    parts = [type(node).__name__, [ast.dump(d) for d in node.decorator_list], [ast.dump(s) for s in body]]
    if isinstance(node, ast.ClassDef):
        parts.append([ast.dump(base) for base in node.bases] + [ast.dump(kw) for kw in node.keywords])
    else:
        parts.append(_args_dump(node.args))  # without annotations (audit H13)
    return repr(parts)


def _args_dump(args: ast.arguments) -> str:
    def name(arg: ast.arg | None) -> str | None:
        return arg.arg if arg is not None else None

    return repr(
        [
            [arg.arg for arg in args.posonlyargs],
            [arg.arg for arg in args.args],
            name(args.vararg),
            [arg.arg for arg in args.kwonlyargs],
            name(args.kwarg),
            [ast.dump(default) for default in args.defaults],
            [ast.dump(default) if default is not None else None for default in args.kw_defaults],
        ]
    )


def _identifiers(node: ast.AST) -> frozenset[str]:
    out: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            out.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            out.add(inner.attr)
        elif isinstance(inner, ast.alias):
            out.add(inner.name.rsplit(".", 1)[-1])
            if inner.asname:
                out.add(inner.asname)
        elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(inner.name)
        elif isinstance(inner, ast.arg):
            out.add(inner.arg)
    return frozenset(out)


# -- JavaScript / TypeScript ------------------------------------------------------------------------

_JS_TITLE = re.compile(r"\b(?:it|test)(?:\.(?:skip|only|todo|concurrent))?\s*\(\s*([\"'`])(.*?)\1")
# `skip:` / `only:` / `todo:` count only as a test call's options object (node:test's
# `test("title", { skip: true }, fn)`): the same keys in data — `{ watch: false, only: "lint" }`
# in an assertion — are not a skip (audit of 66e1617, M7).
_JS_SKIP = re.compile(
    r"\b(?:it|test|describe|suite)\.(?:skip|only|todo)\s*\(|\bx(?:it|describe|test)\s*\(|"
    r"\b(?:it|test|describe|suite)\s*\(\s*(?:\"[^\"\n]*\"|'[^'\n]*'|`[^`\n]*`)\s*,\s*\{[^{}]*"
    r"\b(?:skip|only|todo)\s*:\s*(?:true|['\"])|\bt\.(?:skip|todo)\s*\("
)
_JS_ASSERT = re.compile(
    r"\bassert(?:\.\w+)?\s*\(|\bexpect\s*\(|\bt\.(?:assert\w*|equal|deepEqual|ok|is|throws)\s*\("
)
# Exiting the process early hides a run. Setting `process.exitCode` does not: a CLI test resets it
# after asserting it, and the runner still sets the code for failures (audit of 66e1617, R2-5).
_JS_HACK = re.compile(r"\bprocess\.exit\s*\(")


def _skips_in(text: str, titles: set[str]) -> int:
    """Skips outside any test, and inside the tests titled ``titles`` (those that existed
    before): a skip inside a newly added test weakens nothing (audit of 66e1617, R2-4)."""
    starts = list(_JS_TITLE.finditer(text))
    if not starts:
        return len(_JS_SKIP.findall(text))
    count = len(_JS_SKIP.findall(text[: starts[0].start()]))
    for n, match in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(text)
        if match.group(2) in titles:
            count += len(_JS_SKIP.findall(text[match.start() : end]))
    return count


def _javascript(path: str, before: str, after: str) -> list[Weakening]:
    out: list[Weakening] = []
    old_titles = [title for _, title in _JS_TITLE.findall(before)]
    new_titles = set(title for _, title in _JS_TITLE.findall(after))
    if len(new_titles) < len(set(old_titles)):
        for title in old_titles:
            if title not in new_titles:
                out.append(Weakening(path, title, "deleted", "deleted"))
    existing = set(old_titles)
    if _skips_in(after, existing) > _skips_in(before, existing):
        out.append(Weakening(path, "", "skipped", "skip, only or todo added"))
    if len(_JS_HACK.findall(after)) > len(_JS_HACK.findall(before)):
        out.append(Weakening(path, "", "hack", "a process exit added"))
    if len(_JS_ASSERT.findall(after)) < len(_JS_ASSERT.findall(before)) and len(new_titles) <= len(
        set(old_titles)
    ):
        out.append(
            Weakening(
                path,
                "",
                "fewer-assertions",
                f"{len(_JS_ASSERT.findall(before))} assertion(s) -> {len(_JS_ASSERT.findall(after))}",
            )
        )
    return out


def weakenings(path: str, before: str, after: str | None) -> list[Weakening] | None:
    """How the change weakened an existing test file (``after`` None: deleted). None:
    cannot tell (unparsable, unsupported language)."""
    lower = path.lower()
    if after is None:
        return [Weakening(path, "", "file-deleted", "test file deleted")]
    if lower.endswith(_PY):
        return _python(path, before, after)
    if lower.endswith(_JS):
        return _javascript(path, before, after)
    return None


# -- the request ------------------------------------------------------------------------------------------

_TEST_NOUN = r"(?:tests?|test\s+(?:file|suite|case)s?|specs?|assertions?|fixtures?|snapshots?)"
# "Leave the tests alone". Not "without changing what the tests check" or "don't change the test
# logic": those ask to keep what the tests verify while restructuring them (audit of 66e1617, R2-3).
_KEPT = re.compile(
    rf"\b(?:don'?t|do\s+not|never|without)\s+(?:\w+\s+){{0,2}}(?:chang|edit|modify|touch|alter|updat|delet|remov|skip)\w*\s+"
    rf"(?:\w+\s+){{0,2}}{_TEST_NOUN}\b"
    r"(?!\s+(?:check|test|assert|cover|verif|logic|behaviou?r|coverage|semantics|intent)\w*)"
    rf"|\b(?:leave|keep)\s+(?:the\s+|all\s+|any\s+)?(?:existing\s+)?{_TEST_NOUN}\s+(?:alone|as\s+(?:they|it)\s+(?:are|is)|unchanged|intact|untouched)\b"
    rf"|\b{_TEST_NOUN}\s+(?:are|is)\s+the\s+spec\b"
    rf"|\bthe\s+{_TEST_NOUN}\s+(?:are|is)\s+(?:right|correct|the\s+source\s+of\s+truth)\b",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    rf"\b(?:updat|chang|edit|modif|fix|rewrit|adjust|remov|delet|drop|renam|replac|skip|disabl|quarantin)\w*\s+"
    rf"(?:\w+\s+){{0,3}}{_TEST_NOUN}\b"
    rf"|\b{_TEST_NOUN}\s+(?:is|are)\s+(?:wrong|outdated|out\s+of\s+date|stale|obsolete|flaky|broken|incorrect)\b"
    rf"|\b{_TEST_NOUN}\b[^.!?\n]{{0,40}}\b(?:should|must|needs?\s+to)\s+(?:be\s+)?(?:updat|chang|remov|delet|fix)\w*"
    # a test-maintenance request: port, convert or migrate tests (audit H12)
    rf"|\b(?:port|convert|migrat)\w*\s+(?:\w+\s+){{0,3}}{_TEST_NOUN}\b"
    r"|\b(?:port|convert|migrat)\w*\b[^.!?\n]{0,60}?\b(?:to|into)\s+(?:\w+\s+){0,2}?"
    r"(?:pytest|unittest|jest|vitest|mocha|node:test|rspec)\b",
    re.IGNORECASE,
)


def tests_kept_requested(prompt: str | None) -> bool:
    """The request said to leave the tests alone ("the tests are the spec", "don't change
    the tests")."""
    return bool(_KEPT.search(re.sub(r"\s+", " ", prompt or "")[:20_000]))


_SKIP_REQUEST = re.compile(
    r"\b(?:skip|xfail|x-fail|disabl|quarantin|mark)\w*\s+(?:\w+\s+){0,3}?"
    r"(?:tests?\b|specs?\b|test_\w+|\w+_test\b|[\w./-]+\.(?:test|spec)\.[cm]?[jt]sx?\b|[\w./-]*test[\w./-]*\.py\b)"
    r"|\b(?:test_\w+|tests?)\b[^.!?\n]{0,80}\b(?:skip|xfail|disable|quarantine)\w*\b",
    re.IGNORECASE,
)


def tests_change_requested(prompt: str | None) -> bool:
    """The request asks for test changes ("update the tests", "the test is outdated", "skip
    the flaky test", "xfail test_x for now"), and does not also forbid them."""
    text = re.sub(r"\s+", " ", prompt or "")[:20_000]
    for match in _SKIP_REQUEST.finditer(text):
        if not re.search(
            r"\b(?:don'?t|do\s+not|never|no|without)\s+(?:\w+\s+){0,2}$", text[: match.start()], re.I
        ):
            return True  # a skip asked for is a skip asked for, whatever else the request says
    if tests_kept_requested(text):
        return False
    for match in _CHANGE.finditer(text):
        before = text[max(0, match.start() - 30) : match.start()]
        if not re.search(r"\b(?:don'?t|do\s+not|never|without|no)\s+(?:\w+\s+){0,2}$", before, re.I):
            return True
    return False


# -- the concern -------------------------------------------------------------------------------------------


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The test-weakening concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter

    prompt = state.spec.prompt or ""
    texts = arbiter.changed_texts(state, index)
    found: list[Weakening] = []
    after_all = "\n".join(text for _, text in texts.values() if text)
    before_all = "\n".join(text for text, _ in texts.values() if text)
    targets = spec_integrity.request_targets(prompt)
    code = [(text, now) for path, (text, now) in texts.items() if not scanner.is_test_path(path)]
    code_before = "\n".join(text for text, _ in code if text)
    code_after = "\n".join(now for _, now in code if now)
    for path, (before, after) in texts.items():
        if before is None or not scanner.is_test_path(path):
            continue
        weakened = weakenings(path, before, after)
        for item in weakened or ():
            if item.kind in ("deleted", "file-deleted") and _went_with_code(
                item, before, before_all, after_all, targets
            ):
                continue
            if item.kind in _MODULE_KINDS and (
                _named_or_removed(item, targets, code_before, code_after)
                or any(_gone(name, index.root) for name in item.names if "." in name)  # moved (H10)
                or (item.literals and all(_named_in(value, prompt) for value in item.literals))
            ):
                continue  # the request named it, or it went with its code
            found.append(item)
    requested = tests_change_requested(prompt)
    kept = tests_kept_requested(prompt)
    pressure = spec_integrity.test_pressure_requested(prompt)
    failed = _failed_earlier(state)
    # Module-level changes (Stage 4, rule 2) are kept only where they speak. That means test
    # pressure (the request's, M1, or this very file failing before the task's first change, M2),
    # in a file that failed, and a request that did not ask for test changes. Anywhere else they
    # are ordinary test maintenance, and not even recorded. An import that only gained names
    # moved no existing binding, so it counts only against the request's own yardstick (M1).
    # A requested red phase ("write failing tests first") is not pressure: the failures are the
    # ones it asked for (audit H2).
    from truthstone.verify import claims

    asked = pressure and not claims.red_phase_requested(prompt)
    early = _failed_earlier(state, until=state.first_change_seq or 0)
    found = [
        item
        for item in found
        if item.kind not in _MODULE_KINDS
        or (
            not requested
            and _failed(item, failed)
            and (asked or (item.kind == "module-level" and _failed(item, early)))
        )
    ]
    if not found:
        return []
    speaking = [
        item
        for item in found
        if not requested
        and (item.always or kept or item.kind in _MODULE_KINDS or (pressure and _failed(item, failed)))
    ]
    shown = (speaking or found)[:4]
    listing = "\n".join(f"  - {item.describe()}" for item in shown)
    more = (
        f"\n  - and {len(speaking or found) - len(shown)} more" if len(speaking or found) > len(shown) else ""
    )
    text = (
        "This change weakens existing tests:\n"
        f"{listing}{more}\n"
        "Restore them. If a test contradicts what was asked, report that instead of changing the "
        "test; if the test really should change, say so explicitly."
    )
    finding = arbiter.finding(
        ReasonCategory.TEST_WEAKENING,
        Severity.HIGH if speaking else Severity.LOW,
        summary=f"{len(found)} existing test(s) weakened, deleted or skipped"
        + ("" if speaking else " (recorded only: no prior failure, no prohibition, or requested)"),
        detail="; ".join(item.describe() for item in found[:8]),
        evidence=[
            EvidenceRef(source="filesystem", path=item.path, symbol=item.test or None) for item in shown
        ],
    )
    return [arbiter.Concern(ReasonCategory.TEST_WEAKENING, text, finding, can_speak=bool(speaking))]


def _went_with_code(item: Weakening, before: str, before_all: str, after_all: str, targets: set[str]) -> bool:
    """A deleted test of code the session removed or renamed, or that the request targets."""
    name = item.test.rsplit("::", 1)[-1]
    if any(target and target in name for target in targets):
        return True
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", name.removeprefix("test_")))
    for word in words:
        mentioned = re.compile(rf"(?<![\w$]){re.escape(word)}(?![\w$])")
        if mentioned.search(before_all) and not mentioned.search(after_all):
            return True
    return False


_MODULE_KINDS = frozenset({"module-level", "import-extended"})


def _gone(module: str, root: str) -> bool:
    """An import's module of this repository that is no longer there: its top-level package is
    in the repository (at the root, or under src/ or lib/), the module itself is not. A module
    the session moved or renamed (audit H10); never a standard-library or third-party one."""
    parts = module.split(".")
    if len(parts) < 2 or not all(part.isidentifier() for part in parts):
        return False
    for base in (Path(root), Path(root, "src"), Path(root, "lib")):
        if (base / parts[0]).is_dir():
            rel = Path(base, *parts)
            return not (rel.with_suffix(".py").exists() or (rel / "__init__.py").exists() or rel.is_dir())
    return False


def _named_in(value: str, prompt: str) -> bool:
    """A string value the request itself names (the new data folder it describes, audit H11)."""
    return re.search(rf"(?<![\w.]){re.escape(value)}(?![\w])", prompt, re.IGNORECASE) is not None


def _named_or_removed(item: Weakening, targets: set[str], code_before: str, code_after: str) -> bool:
    """A module-level change the request names (it renames or removes one of the identifiers the
    change touched), or one that went with production code the session removed."""
    if item.names & targets:
        return True
    for name in item.names:
        if len(name) < 5:
            continue  # `rows`, `data`: too common to say the code went
        mentioned = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
        if mentioned.search(code_before) and not mentioned.search(code_after):
            return True
    return False


def _failed_earlier(state: TaskState, until: int | None = None) -> tuple[set[str], set[str]]:
    """(failing test ids, failing test files) of every failing run in this task, or of those
    before the timeline position ``until``."""
    ids: set[str] = set()
    files: set[str] = set()
    for run in state.verification.outcomes:
        if until is not None and (run.seq is None or run.seq >= until):
            continue
        if run.passed is False:
            ids.update(run.failing_tests)
            files.update(run.failing_files)
            files.update(test.split("::", 1)[0] for test in run.failing_tests if "::" in test)
    return ids, files


def _failed(item: Weakening, failed: tuple[set[str], set[str]]) -> bool:
    ids, files = failed
    if item.test:
        name = item.test.rsplit("::", 1)[-1]
        if any(test.split("::")[-1].split("[", 1)[0] == name and item.path in test for test in ids):
            return True
        # An id without its file (some runners report the bare name): the name alone, exactly.
        # Not a substring: `test_totals` is not `tests/test_totals.py::test_totals_currency`
        # (audit of 66e1617, M10).
        if any("::" not in test and test.split("[", 1)[0] in (name, item.test) for test in ids):
            return True
    return (
        any(
            item.path == path or item.path.endswith("/" + path) or path.endswith("/" + item.path)
            for path in files
        )
        and not item.test
    )
