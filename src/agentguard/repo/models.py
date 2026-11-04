"""Records that make up the repository index (SPEC §32).

These are the ground truth the Evidence Engine checks agent claims against, so they use
plain slotted dataclasses rather than pydantic models: an index holds tens of thousands of
them and they are never deserialised from untrusted input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Extension -> language. Only languages we can extract symbols from are listed as
# first-class; everything else is indexed as a file but not parsed.
LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "c_sharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

# Files that configure the project rather than implement it. Changes here have wider
# blast radius than their size suggests, which the Complexity Engine cares about (§12).
CONFIG_FILENAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile",
        "poetry.lock", "uv.lock", "package.json", "package-lock.json", "yarn.lock",
        "pnpm-lock.yaml", "tsconfig.json", "jsconfig.json", "go.mod", "go.sum",
        "Cargo.toml", "Cargo.lock", "Gemfile", "composer.json", "pom.xml",
        "build.gradle", "Makefile", "Dockerfile", "docker-compose.yml",
        "docker-compose.yaml", ".env", ".env.example", "alembic.ini", "tox.ini",
        ".eslintrc.json", ".prettierrc", "vite.config.ts", "next.config.js",
        "webpack.config.js", "jest.config.js", "vitest.config.ts", "pytest.ini",
    }
)

CONFIG_SUFFIXES: tuple[str, ...] = (".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf")
CONFIG_DIRS: frozenset[str] = frozenset(
    {"config", "configs", "settings", ".github", "k8s", "helm", "terraform"}
)


@dataclass(slots=True)
class FileRecord:
    path: str  # repo-relative, posix separators
    size: int
    mtime_ns: int
    lang: str
    is_test: bool = False
    is_config: bool = False

    @property
    def parsable(self) -> bool:
        return self.lang in {
            "python", "javascript", "typescript", "tsx", "go", "rust", "java", "ruby",
        }


@dataclass(slots=True)
class SymbolRecord:
    """A definition that actually exists in the repository.

    `qualname` is what an agent usually claims (`UserRepository.get_active_users`);
    `name` is what it sometimes claims (`get_active_users`). Both are indexed.
    """

    name: str
    qualname: str
    kind: str  # function | method | class | constant | variable | interface | type
    path: str
    line: int
    end_line: int = 0
    parent: str | None = None
    signature: str = ""

    # Base classes, and whether the extractor was actually able to determine them.
    # `bases_known=False` means "this extractor does not report inheritance", which must
    # be read as "the attribute set of this type is unknown" — a class inheriting from
    # something invisible has methods we cannot see, and challenging a call to one of
    # them would be a false positive.
    bases: tuple[str, ...] = ()
    bases_known: bool = False

    @property
    def is_private(self) -> bool:
        return self.name.startswith("_") and not self.name.startswith("__")


@dataclass(slots=True)
class ImportRecord:
    raw: str  # the module string as written: "os.path", "./utils", "react"
    names: list[str] = field(default_factory=list)  # imported symbol names
    alias: str | None = None
    line: int = 0
    level: int = 0  # relative-import depth; 0 = absolute
    resolved: str | None = None  # repo-relative path this resolves to, if internal
    # The names this import binds in the importing module, `as` names included:
    # `from .impl import Thing as Public` binds "Public", which `names` does not say.
    # Empty when the extractor does not report it, and for a star import.
    bound: list[str] = field(default_factory=list)

    @property
    def is_relative(self) -> bool:
        return self.level > 0 or self.raw.startswith(".")

    @property
    def is_internal(self) -> bool:
        return self.resolved is not None

    @property
    def is_star(self) -> bool:
        return "*" in self.names


@dataclass(frozen=True, slots=True)
class ModuleExports:
    """What a Python module offers `from module import ...` beyond its own bindings (E1).

    The Evidence Engine may only say "`X` is not in `module`" when the module's namespace
    is decidable from its source. These flags say when it is not.
    """

    # The literal `__all__`: the names `from module import *` binds. Set only for one
    # unconditional top-level assignment of a list/tuple of string literals.
    all_names: tuple[str, ...] | None = None
    # `__all__` exists but is not such a literal (computed, extended, conditional,
    # assigned twice, imported): what a star import of this module binds is undecidable.
    all_dynamic: bool = False
    # A module-level `__getattr__` (PEP 562): `from module import ANYTHING` may succeed.
    getattr_hook: bool = False
    # The module writes its own namespace (`globals()`, `vars()`, `exec`,
    # `sys.modules[__name__]`): which names it has is undecidable.
    dynamic_namespace: bool = False


@dataclass(slots=True)
class GitState:
    """Cheap, frequently-refreshed git facts (SPEC §14 evidence sources)."""

    is_repo: bool = False
    branch: str = ""
    head: str = ""
    dirty: set[str] = field(default_factory=set)
    untracked: set[str] = field(default_factory=set)
    recent_commits: list[tuple[str, int, str]] = field(default_factory=list)  # (sha, ts, subject)
    churn: dict[str, int] = field(default_factory=dict)  # path -> commits touching it


@dataclass(slots=True)
class DependencyInfo:
    """Declared dependencies, per manifest (SPEC §14, §16 DEPENDENCY challenge)."""

    runtime: dict[str, str] = field(default_factory=dict)  # name -> version spec
    dev: dict[str, str] = field(default_factory=dict)
    manifests: list[str] = field(default_factory=list)

    def declares(self, package: str) -> bool:
        key = package.lower().replace("_", "-")
        return any(
            key == name.lower().replace("_", "-") for name in (*self.runtime, *self.dev)
        )

    @property
    def all_names(self) -> set[str]:
        return set(self.runtime) | set(self.dev)
