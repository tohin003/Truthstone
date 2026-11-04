"""Python symbol and import extraction via the stdlib `ast` module.

Python gets its own extractor rather than going through tree-sitter because `ast` is
already installed, faster, and exact — it is the same parser the interpreter uses, so
there is no grammar-version drift between what AgentGuard believes and what Python does.
"""

from __future__ import annotations

import ast
import re

from agentguard.repo.models import ImportRecord, ModuleExports, SymbolRecord

_MAX_SIGNATURE = 200

# A module that can write its own namespace: `globals()`, a bare `exec(...)`, `vars()`
# with no argument, or `sys.modules[__name__]`. Matched on the source text, comments and
# strings included: a stray mention only makes the module undecidable (silence). Plain
# substring checks first, because even a regex costs ~0.4 s across a 900-file repo.
_NAMESPACE_MARKERS: tuple[str, ...] = ("globals(", "exec(", "vars(", "sys.modules[")
_NAMESPACE_CALL = re.compile(r"(globals|exec|vars)\s*\((\s*\))?|sys\.modules\s*\[\s*__name__\b")


def _writes_own_namespace(source: str) -> bool:
    if not any(marker in source for marker in _NAMESPACE_MARKERS):
        return False
    for match in _NAMESPACE_CALL.finditer(source):
        start = match.start()
        if start and (source[start - 1].isalnum() or source[start - 1] in "_."):
            continue  # `subprocess_exec(`, `cursor.exec(`: another name, or a method
        if match.group(1) == "vars" and match.group(2) is None:
            continue  # `vars(obj)` reads an object
        return True
    return False


def _unpacked(target: ast.expr) -> list[ast.expr]:
    """The leaves an assignment target binds: `a, (b, *c) = ...` -> [a, b, c]."""
    if isinstance(target, ast.Tuple | ast.List):
        return [leaf for element in target.elts for leaf in _unpacked(element)]
    if isinstance(target, ast.Starred):
        return _unpacked(target.value)
    return [target]


def _walrus_targets(statement: ast.stmt) -> list[ast.Name]:
    """Names bound by `:=` in a statement's own expressions, in the statement's scope.

    Nested statements are visited on their own, and a lambda (like a def or a class) has
    its own scope. A comprehension does not: `:=` inside one binds in the enclosing scope.
    """
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return []
    found: list[ast.Name] = []
    stack = [
        child
        for child in ast.iter_child_nodes(statement)
        if not isinstance(child, ast.stmt | ast.ExceptHandler | ast.match_case)
    ]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            found.append(node.target)
        stack.extend(ast.iter_child_nodes(node))
    return found


def _literal_strings(node: ast.expr | None) -> tuple[str, ...] | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values: list[str] = []
    for element in node.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        values.append(element.value)
    return tuple(values)


def _module_exports(tree: ast.Module, source: str, module_bound: set[str]) -> ModuleExports:
    """`__all__`, PEP 562 `__getattr__` and namespace writes, as `ModuleExports` (E1).

    Ported from Pebble's `_Module.exported` (backend/pebble/python_xref.py, same owner,
    Apache-2.0): a literal `__all__` decides what a star import binds; a computed,
    extended or repeatedly assigned one makes it undecidable. Stricter than the original:
    mutation through a method (`__all__.extend(...)`), conditional assignment and an
    imported `__all__` also make it undecidable.
    """
    getattr_hook = "__getattr__" in module_bound
    dynamic_namespace = _writes_own_namespace(source)
    if "__all__" not in source:
        return ModuleExports(getattr_hook=getattr_hook, dynamic_namespace=dynamic_namespace)

    stores = 0
    mutated = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__all__":
            if isinstance(node.ctx, ast.Store):
                stores += 1
            elif isinstance(node.ctx, ast.Del):
                mutated = True
        elif isinstance(node, ast.Global | ast.Nonlocal) and "__all__" in node.names:
            mutated = True
        elif isinstance(node, ast.alias) and (node.asname or node.name) == "__all__":
            mutated = True  # `from .impl import __all__`: someone else's list decides
        elif (
            isinstance(node, ast.Attribute | ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "__all__"
            and (isinstance(node, ast.Attribute) or not isinstance(node.ctx, ast.Load))
        ):
            mutated = True  # `__all__.extend(...)`, `__all__[0] = ...`

    literal: tuple[str, ...] | None = None
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if len(targets) == 1 and isinstance(targets[0], ast.Name) and targets[0].id == "__all__":
            literal = _literal_strings(value)

    flags = {"getattr_hook": getattr_hook, "dynamic_namespace": dynamic_namespace}
    if stores == 0 and not mutated:
        return ModuleExports(**flags)
    if stores == 1 and literal is not None and not mutated:
        return ModuleExports(all_names=literal, **flags)
    return ModuleExports(all_dynamic=True, **flags)


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args = ast.unparse(node.args)
    except Exception:  # noqa: BLE001 - unparse can fail on exotic trees
        args = "..."
    returns = ""
    if node.returns is not None:
        try:
            returns = f" -> {ast.unparse(node.returns)}"
        except Exception:  # noqa: BLE001
            returns = ""
    return f"({args}){returns}"[:_MAX_SIGNATURE]


def _base_names(node: ast.ClassDef) -> tuple[str, ...]:
    names: list[str] = []
    for base in node.bases:
        try:
            names.append(ast.unparse(base))
        except Exception:  # noqa: BLE001
            names.append("<unparseable>")
    return tuple(names)


def extract(source: str, path: str) -> tuple[list[SymbolRecord], list[ImportRecord], bool]:
    """Returns (symbols, imports, clean_parse).

    `clean_parse` is not cosmetic. "Parsed cleanly and found no symbols" and "could not
    parse at all" look identical in the symbol lists but mean opposite things: only the
    first licenses the conclusion that a symbol is *absent*. Conflating them would make
    every syntax error a source of false hallucination challenges (SPEC §14).

    Unparsable source is routine — the agent is often mid-edit — so this never raises.
    """
    symbols, imports, clean, _exports = extract_module(source, path)
    return symbols, imports, clean


def extract_module(
    source: str, path: str
) -> tuple[list[SymbolRecord], list[ImportRecord], bool, ModuleExports | None]:
    """`extract`, plus what the module offers `from module import ...` (E1).

    Returns (symbols, imports, clean_parse, exports); `exports` is None when the source
    does not parse.

    At module and class level every binding form counts, not just `name = ...`: tuple
    and list unpacking (`LOW, HIGH = 1, 10`), `for` and `with` targets, `:=`, `type`
    aliases, and `global` declarations made inside functions. In methods, unpacked
    instance attributes (`self.a, self.b = a, b`) count too. A name bound any of these
    ways used to be reported as absent: a false challenge on working code.
    """
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError):
        return [], [], False, None

    symbols: list[SymbolRecord] = []
    imports: list[ImportRecord] = []
    module_bound: set[str] = set()  # names bound in the module's own namespace
    walrus = ":=" in source  # no `:=` token, no walrus targets to look for

    def add(name: str, node: ast.AST, parent: str | None, scope: str, kind: str = "") -> None:
        symbols.append(
            SymbolRecord(
                name=name,
                qualname=f"{parent}.{name}" if parent else name,
                kind=kind or ("constant" if name.isupper() else "variable"),
                path=path,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                parent=parent,
            )
        )
        if scope == "module":
            module_bound.add(name)

    def add_attribute(target: ast.Attribute, node: ast.AST, enclosing_class: str | None) -> None:
        # `self.root = ...` inside a method is an attribute of the class, not of the
        # method. Missing these made every instance attribute look like a hallucination
        # — the single largest source of false positives found in the Phase 3 audit
        # against real code.
        symbols.append(
            SymbolRecord(
                name=target.attr,
                qualname=f"{enclosing_class}.{target.attr}",
                kind="attribute",
                path=path,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                parent=enclosing_class,
            )
        )

    def self_attribute(target: ast.expr, enclosing_class: str | None) -> bool:
        return (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and bool(enclosing_class)
        )

    def visit(
        node: ast.AST, parent: str | None, enclosing_class: str | None = None, scope: str = "module"
    ) -> None:
        binding_scope = scope in ("module", "class")
        for child in ast.iter_child_nodes(node):
            if binding_scope and walrus and isinstance(child, ast.stmt):
                for target in _walrus_targets(child):
                    add(target.id, child, parent, scope)

            if isinstance(child, ast.ClassDef):
                qualname = f"{parent}.{child.name}" if parent else child.name
                bases = _base_names(child)
                symbols.append(
                    SymbolRecord(
                        name=child.name,
                        qualname=qualname,
                        kind="class",
                        path=path,
                        line=child.lineno,
                        end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        parent=parent,
                        signature=f"({', '.join(bases)})" if bases else "",
                        bases=bases,
                        bases_known=True,
                    )
                )
                if scope == "module":
                    module_bound.add(child.name)
                visit(child, qualname, qualname, "class")

            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qualname = f"{parent}.{child.name}" if parent else child.name
                symbols.append(
                    SymbolRecord(
                        name=child.name,
                        qualname=qualname,
                        kind="method" if parent else "function",
                        path=path,
                        line=child.lineno,
                        end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        parent=parent,
                        signature=_signature(child),
                    )
                )
                if scope == "module":
                    module_bound.add(child.name)
                # Nested defs are indexed too — a closure is still a real definition.
                visit(child, qualname, enclosing_class, "function")

            elif isinstance(child, ast.Assign | ast.AnnAssign):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        add(target.id, child, parent, scope)
                    elif self_attribute(target, enclosing_class):
                        add_attribute(target, child, enclosing_class)
                    elif isinstance(target, ast.Tuple | ast.List):
                        # `LOW, HIGH = 1, 10` binds both; so does `self.a, self.b = a, b`.
                        for leaf in _unpacked(target):
                            if isinstance(leaf, ast.Name) and binding_scope:
                                add(leaf.id, child, parent, scope)
                            elif self_attribute(leaf, enclosing_class):
                                add_attribute(leaf, child, enclosing_class)

            elif isinstance(child, ast.TypeAlias):
                if binding_scope and isinstance(child.name, ast.Name):
                    add(child.name.id, child, parent, scope, kind="type")

            elif isinstance(child, ast.Global):
                # `global CONFIG` then `CONFIG = load()` inside a function creates a module
                # attribute that no module-level statement mentions.
                for name in child.names:
                    add(name, child, None, "module")

            elif isinstance(child, ast.Import):
                for alias in child.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    imports.append(
                        ImportRecord(
                            raw=alias.name,
                            names=[alias.name.split(".")[0]],
                            alias=alias.asname,
                            line=child.lineno,
                            bound=[bound],
                        )
                    )
                    if scope == "module":
                        module_bound.add(bound)

            elif isinstance(child, ast.ImportFrom):
                bound = [a.asname or a.name for a in child.names if a.name != "*"]
                imports.append(
                    ImportRecord(
                        raw=child.module or "",
                        names=[a.name for a in child.names],
                        alias=None,
                        line=child.lineno,
                        level=child.level or 0,
                        bound=bound,
                    )
                )
                if scope == "module":
                    module_bound.update(bound)

            else:
                if binding_scope and isinstance(child, ast.For | ast.AsyncFor):
                    for leaf in _unpacked(child.target):
                        if isinstance(leaf, ast.Name):
                            add(leaf.id, child, parent, scope)
                elif binding_scope and isinstance(child, ast.With | ast.AsyncWith):
                    for item in child.items:
                        for leaf in _unpacked(item.optional_vars) if item.optional_vars else ():
                            if isinstance(leaf, ast.Name):
                                add(leaf.id, child, parent, scope)
                # Descend through if/try/with/for so conditionally-defined symbols are found.
                if isinstance(child, ast.If | ast.Try | ast.With | ast.AsyncWith | ast.For | ast.AsyncFor):
                    visit(child, parent, enclosing_class, scope)

    visit(tree, None, None, "module")
    return symbols, imports, True, _module_exports(tree, source, module_bound)


def extract_referenced_attributes(source: str) -> set[tuple[str, str]]:
    """Find `Something.method` references — the shape of a SPEC §14 claim.

    Returns (receiver, attribute) pairs, e.g. ("UserRepository", "get_active_users") from
    `UserRepository.get_active_users()`. Used by the Evidence Engine in Phase 3 to spot
    calls to methods that do not exist.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()

    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            out.add((node.value.id, node.attr))
    return out


def defined_names(source: str) -> set[str]:
    """Every name this source *defines* or binds locally.

    The Evidence Engine must never flag a symbol the agent is creating in the very edit
    being checked — that false positive would make AgentGuard unusable (SPEC §14).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names
