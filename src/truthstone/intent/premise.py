"""False-premise grounding at prompt time (M8, WP7).

A request can rest on something that is not there: "fetchkit already logs every request when
``X_DEBUG=1`` is set, so switch that on in CI", "build it on the existing ``Store.move()``",
"pass the ``--dry-run`` flag". An agent that takes the premise on trust does exactly what was
asked — sets the switch — and reports success, while nothing reads it. This module finds the
names a prompt **asserts exist or already work** and checks them against the repository. When
one appears **nowhere** in it — no code, config (TOML, YAML, JSON, ``.env``, CI files), docs or
path — the agent gets ONE note before it starts:

    `X_DEBUG` appears nowhere in this repository; the behaviour the request assumes may not
    exist — verify before building on it, and tell the user if it doesn't.

Precision comes first: a note on an ordinary request is friction, and the note must never fire
on routine work.

* **Only asserted names.** A code-like name (an environment variable, a dotted or called
  symbol, a backticked name, a ``--flag``, a path) counts only in a sentence that asserts it
  exists: "already", "existing", "use/call/reuse/build on/on top of", "the … helper, flag,
  setting …", or a request to switch a named setting on ("enable", "turn/switch … on", "set").
* **Never a name being created.** "add", "implement", "create", "introduce", "new", "define",
  "declare", "support", "rename … to", "becomes" just before the name: the request is to make
  it, and of course it is not there yet.
* **Zero occurrences**, or **a switch nothing reads.** A name with no whole-word occurrence
  anywhere in the repository's text gets the note. So does a named switch (an environment
  variable, a config key, a flag) that the request says *already* works ("already",
  "existing", "currently", "is supposed to", "should already") when it occurs only in files
  that are not code (config, data, docs, CI) and no code file mentions it:

      `X_DEBUG` appears only in README.md, and no code in this repository reads it; the
      behaviour the request assumes may not exist — verify before building on it, and tell
      the user if it doesn't.

  Any other occurrence resolves the name. A dotted name also resolves through its last part in
  code (``Store.move`` through any ``move`` in a source file).
* **Never another program's switch.** Keys of tool-owned configuration (``tsconfig.json``,
  ``package.json``, ``pyproject.toml``, lint and test-runner configs: the tool reads them) and
  well-known runtime and tool environment variables (``NODE_*``, ``PYTHON*``, ``CI``,
  ``GITHUB_*``, ``DEBUG``, ``NO_COLOR``…) never get a note.
* **External things are skipped:** URLs, package specs (``@scope/pkg``, ``node:fs``), HTTP
  headers, versions, dates, numbers.
* Silent while the index is not built, and once per name per session (the caller keeps that).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from truthstone.core.enums import ChallengeCategory, EscalationLevel, FailureMode, Severity, Verdict
from truthstone.core.models import EvidenceRef, Finding

SUBJECT = "false_premise"  # the intervention kind (core/profile.py)
NOTE = (
    "{names} {verb} nowhere in this repository; the behaviour the request assumes may not exist — "
    "verify before building on it, and tell the user if it doesn't."
)
ONLY_IN = "`{name}` appears only in {files}, and no code in this repository reads it"
TAIL = (
    "the behaviour the request assumes may not exist — verify before building on it, and tell the "
    "user if it doesn't."
)
# A request that says the behaviour exists today: the only kind a switch-nobody-reads note answers.
_EXISTING_BEHAVIOUR = re.compile(
    r"\b(?:already|existing|currently|(?:is|are) supposed to|should already)\b", re.IGNORECASE
)
# Environment variables a runtime or a tool reads, not the project's code.
_WELL_KNOWN_ENV = re.compile(
    r"^(?:CI|DEBUG|NO_COLOR|FORCE_COLOR|CLICOLOR(?:_FORCE)?|TERM|HOME|PATH|LANG|USER|SHELL|TMPDIR|TZ|PWD|"
    r"EDITOR|PAGER|VIRTUAL_ENV|(?:HTTPS?|NO|ALL)_PROXY|"
    r"(?:NODE|NPM|YARN|PNPM|PIP|UV|CONDA|GITHUB|RUNNER|ACTIONS|GITLAB|CIRCLE|TRAVIS|BUILDKITE|JENKINS|"
    r"AWS|AZURE|GOOGLE|GCLOUD|DOCKER|KUBE|JAVA|GRADLE|MAVEN|CARGO|RUSTUP|RUST|LC|XDG|SSH|GIT|PYTEST|"
    r"COVERAGE|TOX|HOMEBREW|OTEL|CUDA|VSCODE)_\w*|PYTHON\w*|GO[A-Z]+)$"
)

# What a scan of the repository may cost at prompt time.
MAX_FILE_BYTES = 1_000_000
MAX_SCAN_BYTES = 64_000_000

# -- the names a prompt can assert --------------------------------------------------------

_ENV = re.compile(r"(?<![\w$])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![\w])")
_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![\w-])")
_BACKTICK = re.compile(r"`([^`\n]{1,120})`")
# `pkg.mod.name`, `Class.method()`: two or more dotted parts, letters first.
_DOTTED = re.compile(r"(?<![\w./-])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)(\(\))?(?![\w/-])")
# `snake_case()`, `camelCase()`: a call, or a name with an underscore or an inner capital.
_CALL = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\(")
_SNAKE = re.compile(r"(?<![\w./-])([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?![\w/-])")
_CAMEL = re.compile(r"(?<![\w./-])([a-z]+(?:[A-Z][a-z0-9]+)+)(?![\w/-])")
_PATH = re.compile(r"(?<![\w@:/.-])((?:\.{1,2}/)?(?:[\w.-]+/)+[\w.-]*)(?![\w/-])")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")

# Existence, anywhere in the sentence: it says the name is there already, or asks to switch a
# named setting on ("… when X=1 is set: turn that on").
_EXISTS = re.compile(
    r"\b(?:already|existing|currently|(?:is|are) supposed to|"
    r"(?:switch|switches|switching|turn|turns|turning|flip|flipping)\b[^.?!\n]{0,40}?\bon)\b",
    re.IGNORECASE,
)
# A sentence whose request is to make something ("Add …", "Please make it …"): only "already"
# or "existing" right before a name can assert it there.
_CREATING_SENTENCE = re.compile(
    r"^\W*(?:(?:please|pls|kindly|so|and|then|now|also|just)\s+)*"
    r"(?:(?:can|could|would|will) you\s+|(?:i|we) (?:need|want) (?:you )?to\s+|let'?s\s+)?"
    r"(?:add|make|implement|create|introduce|write|build|define|declare|support|wire|expose|"
    r"generate|teach|extend|give)\b",
    re.IGNORECASE,
)
# Existence, in the few words just before the name: "use X", "call X", "set X", "build it on X".
_EXISTS_NEAR = re.compile(
    r"\b(?:already|existing|current|reuse|reuses|use|uses|using|call|calls|calling|invoke|via|"
    r"enable|on top of|based on|build (?:it |this |that )?(?:on|upon))\b",
    re.IGNORECASE,
)
# A kind noun after the name: "the X helper", "the --foo flag".
_KIND_NOUN = re.compile(
    r"\s*[`)]?\s*(?:helper|function|method|class|module|flag|option|switch|setting|key|"
    r"variable|env(?:ironment)? var(?:iable)?|config|command|subcommand)s?\b",
    re.IGNORECASE,
)
# Creation: the name is what the request makes.
_CREATES = re.compile(
    r"\b(?:add|adds|adding|added|introduce|introduces|introducing|create|creates|creating|"
    r"implement|implements|implementing|new|define|defines|defining|declare|declares|"
    r"support|supports|supporting|write|writes|writing|rename[sd]?|renaming|becomes?|"
    r"optional|make|makes|making|wire|expose|exposes|generate|generates|need|needs|want)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n\s*\n|(?<=[.!?])$")
_WORD = re.compile(r"[A-Za-z]+")


@dataclass(slots=True)
class Assertion:
    """A name the prompt treats as already there."""

    name: str  # as the prompt wrote it
    kind: str  # env / flag / symbol / path / name
    keys: tuple[str, ...]  # what to look for in the repository's text
    existing: bool = False  # its sentence says the behaviour exists today ("already", ...)


@dataclass(slots=True)
class Premise:
    """The names that resolve to nothing, and the note to give."""

    missing: list[Assertion] = field(default_factory=list)
    # name -> the non-code files it occurs in, for a switch that only those mention
    only_in: dict[str, list[str]] = field(default_factory=dict)

    @property
    def note(self) -> str:
        if not self.missing:
            return ""
        nowhere = [a for a in self.missing if a.name not in self.only_in][:3]
        parts = []
        if nowhere:
            shown = [f"`{a.name}`" for a in nowhere]
            names = shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]
            parts.append(f"{names} {'appears' if len(shown) == 1 else 'appear'} nowhere in this repository")
        for a in [a for a in self.missing if a.name in self.only_in][:3]:
            files = self.only_in[a.name]
            listed = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
            parts.append(ONLY_IN.format(name=a.name, files=listed))
        return "; ".join(parts) + "; " + TAIL

    def finding(self) -> Finding | None:
        if not self.missing:
            return None
        listed = ", ".join(a.name for a in self.missing)
        return Finding(
            category=ChallengeCategory.ASSUMPTION,
            verdict=Verdict.CONTRADICTED,
            failure_mode=FailureMode.UNSUPPORTED_ASSUMPTION,
            severity=Severity.MEDIUM,
            subject=SUBJECT,
            summary=f"the request assumes {listed}, which nothing in the repository has or reads",
            detail=self.note,
            evidence=[
                EvidenceRef(
                    source="filesystem",
                    symbol=a.name,
                    note=f"only in {', '.join(self.only_in[a.name][:3])}"
                    if a.name in self.only_in
                    else "no occurrence",
                )
                for a in self.missing
            ],
            level=EscalationLevel.REPOSITORY,
        )


# -- extraction ---------------------------------------------------------------------------


def _sentences(text: str) -> list[tuple[int, str]]:
    """(offset, sentence) pairs. A dot inside a name (``a.b``, ``ci.yml``) does not end one."""
    out, start = [], 0
    for match in _SENTENCE.finditer(text):
        if match.start() > start:
            out.append((start, text[start : match.start()]))
        start = match.end()
    if start < len(text):
        out.append((start, text[start:]))
    return out


def _external(name: str) -> bool:
    """Things a repository does not define: URLs, package specs, headers, versions, dates."""
    lowered = name.lower()
    return (
        "://" in name
        or lowered.startswith(("www.", "node:", "@", "x-", "http"))
        or re.fullmatch(r"v?\d+(?:[.\-/]\d+)*\w*", name) is not None
        or (re.fullmatch(r"[A-Z/:\-]+", name) is not None and not _ENV.fullmatch(name))
    )


def _candidates(sentence: str) -> list[tuple[int, Assertion]]:
    """Every code-like name in a sentence, with its offset."""
    found: dict[str, tuple[int, Assertion]] = {}

    def put(offset: int, assertion: Assertion) -> None:
        if assertion.name not in found and not _external(assertion.name):
            found[assertion.name] = (offset, assertion)

    for m in _ENV.finditer(sentence):
        if not _WELL_KNOWN_ENV.match(m.group(1)):
            put(m.start(1), Assertion(m.group(1), "env", (m.group(1),)))
    for m in _FLAG.finditer(sentence):
        flag = m.group(1)
        bare = flag[2:]
        put(m.start(1), Assertion(flag, "flag", (flag, bare, bare.replace("-", "_"))))
    for m in _PATH.finditer(sentence):
        path = m.group(1).rstrip(".")
        last = path.rstrip("/").rpartition("/")[2]
        if (path.endswith("/") or _EXTENSION.search(last)) and any(c.islower() for c in path):
            put(m.start(1), Assertion(path, "path", (path.rstrip("/"),)))
    for m in _DOTTED.finditer(sentence):
        dotted = m.group(1)
        if _EXTENSION.search(dotted) and not m.group(2):
            continue  # a file name (`export.py`), not a member
        last = dotted.rpartition(".")[2]
        put(m.start(1), Assertion(dotted + (m.group(2) or ""), "symbol", (dotted, last)))
    for m in _CALL.finditer(sentence):
        put(m.start(1), Assertion(m.group(1) + "()", "symbol", (m.group(1),)))
    for pattern in (_SNAKE, _CAMEL):
        for m in pattern.finditer(sentence):
            put(m.start(1), Assertion(m.group(1), "name", (m.group(1),)))
    for m in _BACKTICK.finditer(sentence):
        inner = m.group(1).strip()
        if re.fullmatch(r"[A-Za-z_][\w-]*", inner) and len(inner) >= 3:
            put(m.start(1), Assertion(inner, "name", (inner,)))
    return sorted(found.values(), key=lambda item: item[0])


def _window(before: str) -> str:
    return " ".join(_WORD.findall(before)[-4:])


def _asserted(sentence: str, offset: int, name: str) -> bool:
    """Whether this sentence asserts that ``name`` (at ``offset``) is already there."""
    before = sentence[:offset]
    after = sentence[offset + len(name) :]
    window = _window(before)
    if re.search(r"\b(?:already|existing)\b", window, re.IGNORECASE):
        return True  # "on top of the existing X": nearest word wins
    # Creation binds tighter than the sentence: a creating word within the four words before.
    if _CREATES.search(window):
        return False
    if _EXISTS_NEAR.search(window):
        return True
    if _CREATING_SENTENCE.search(sentence):
        return False
    if _KIND_NOUN.match(after) and re.search(r"\b(?:the|our|its|their|your)\s+\S*$", before, re.IGNORECASE):
        return True  # "the X helper", "the --foo flag"
    return _EXISTS.search(sentence) is not None


def assertions(prompt: str) -> list[Assertion]:
    """The names a prompt asserts exist, in order, without names it asks to create."""
    created: set[str] = set()
    out: dict[str, Assertion] = {}
    for _start, sentence in _sentences(prompt or ""):
        existing = _EXISTING_BEHAVIOUR.search(sentence) is not None
        for offset, candidate in _candidates(sentence):
            if _asserted(sentence, offset, candidate.name):
                candidate.existing = existing
                out.setdefault(candidate.name, candidate)
            elif _CREATES.search(_window(sentence[:offset])):
                created.add(candidate.name)
    # A name the request creates anywhere is not a premise anywhere.
    return [a for name, a in out.items() if name not in created]


# -- resolution ---------------------------------------------------------------------------


_CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".kt",
        ".swift",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".cs",
        ".php",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".mk",
        ".lua",
        ".pl",
        ".r",
        ".scala",
        ".dart",
        ".ex",
        ".exs",
        ".erl",
        ".clj",
        ".vue",
        ".svelte",
    }
)
_CODE_NAMES = frozenset({"makefile", "gnumakefile", "justfile", "rakefile", "dockerfile", "containerfile"})
# Configuration a tool reads, not the project's code: a key in one is that tool's switch.
_TOOL_OWNED = re.compile(
    r"^(?:tsconfig.*\.json|jsconfig.*\.json|package(?:-lock)?\.json|npm-shrinkwrap\.json|yarn\.lock|"
    r"pnpm-(?:lock|workspace)\.yaml|\.npmrc|\.yarnrc.*|pyproject\.toml|setup\.cfg|tox\.ini|pytest\.ini|"
    r"\.flake8|\.?pylintrc|\.?mypy\.ini|\.?ruff\.toml|\.coveragerc|\.isort\.cfg|pipfile(?:\.lock)?|"
    r"poetry\.lock|uv\.lock|requirements.*\.txt|constraints.*\.txt|cargo\.(?:toml|lock)|go\.(?:mod|sum)|"
    r"gemfile(?:\.lock)?|\.rubocop\.ya?ml|\.eslintrc.*|eslint\.config\..*|\.prettierrc.*|"
    r"prettier\.config\..*|\.stylelintrc.*|jest\.config\..*|vitest\.config\..*|vite\.config\..*|"
    r"webpack\.config\..*|rollup\.config\..*|babel\.config\..*|\.babelrc.*|\.browserslistrc|"
    r"\.editorconfig|\.pre-commit-config\.ya?ml|\.golangci\.ya?ml|\.clang-(?:format|tidy)|"
    r"renovate\.json5?|\.renovaterc.*|dependabot\.ya?ml|\.git(?:ignore|attributes)|\.dockerignore|"
    r"\.nvmrc|\.node-version|\.python-version|\.tool-versions|\.?codecov\.ya?ml|lerna\.json|nx\.json|"
    r"turbo\.json|deno\.jsonc?|bunfig\.toml)$",
    re.IGNORECASE,
)


def _code_file(path: str) -> bool:
    name = path.rpartition("/")[2]
    lowered = name.lower()
    return (
        Path(lowered).suffix in _CODE_SUFFIXES
        or lowered in _CODE_NAMES
        or lowered.startswith(("dockerfile.", "makefile."))
    )


def _tool_owned(path: str) -> bool:
    return _TOOL_OWNED.match(path.rpartition("/")[2]) is not None


# The kinds a "switch nobody reads" note is about: not a symbol or a path.
_SWITCH_KINDS = frozenset({"env", "name", "flag"})


def resolve(
    assertions_: Iterable[Assertion], root: Path, files: Iterable[str]
) -> list[tuple[Assertion, list[str]]]:
    """The assertions the repository does not back, each with the non-code files it occurs in:
    ``[]`` for no occurrence at all (no file at the path, no whole-word occurrence of a key in
    any text file; a dotted name's last part only counts in code), or the files, for a switch
    asserted to work already that no code file and no tool's configuration mentions. Unknown
    or unreadable means resolved: precision first."""
    pending = list(assertions_)
    if not pending:
        return []
    files = list(files)
    present = set(files)
    names = {p.rpartition("/")[2] for p in files}
    unresolved: list[Assertion] = []
    patterns: dict[str, re.Pattern[str]] = {}
    for assertion in pending:
        if assertion.kind == "path":
            path = assertion.keys[0].removeprefix("./")
            if (
                path in present
                or any(p.startswith(path + "/") for p in present)
                or path.rpartition("/")[2] in names
                or (root / path).exists()
            ):
                continue
        unresolved.append(assertion)
    if not unresolved:
        return []
    for assertion in unresolved:
        for key in assertion.keys:
            if key not in patterns:
                patterns[key] = re.compile(rf"(?<![\w-]){re.escape(key)}(?![\w-])")
    # A dotted name's last part (`move` of `Store.move`) only counts in code.
    tails = {a.keys[-1] for a in unresolved if a.kind == "symbol" and len(a.keys) > 1}
    found: set[str] = set()  # in code, or in a tool's configuration: resolved
    elsewhere: dict[str, list[str]] = {}  # only in other files (config, data, docs, CI)
    budget = MAX_SCAN_BYTES
    for rel in files:
        if len(found) == len(patterns):
            break
        try:
            full = root / rel
            size = full.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            budget -= size
            if budget < 0:
                return []  # too big to be sure: say nothing
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        code = _code_file(rel)
        read_here = code or _tool_owned(rel)
        for key, pattern in patterns.items():
            if key in found or key not in text:
                continue
            if not code and key in tails:
                continue  # `move` in prose is not `Store.move`
            if pattern.search(text):
                if read_here:
                    found.add(key)
                else:
                    elsewhere.setdefault(key, []).append(rel)
    out: list[tuple[Assertion, list[str]]] = []
    for assertion in unresolved:
        if any(key in found for key in assertion.keys):
            continue
        only = sorted({rel for key in assertion.keys for rel in elsewhere.get(key, [])})
        if not only:
            out.append((assertion, []))
        elif assertion.existing and assertion.kind in _SWITCH_KINDS:
            out.append((assertion, only))
    return out


def check(prompt: str, root: Path, files: Iterable[str] | None, already: set[str] | None = None) -> Premise:
    """The premise note for ``prompt``: the asserted names nothing in ``root`` has. Silent
    without a file list (the index is not built) and for names already noted."""
    if files is None or not prompt:
        return Premise()
    asserted = [a for a in assertions(prompt) if not already or a.name not in already]
    if not asserted:
        return Premise()
    unbacked = resolve(asserted, root, files)
    return Premise(missing=[a for a, _ in unbacked], only_in={a.name: only for a, only in unbacked if only})
