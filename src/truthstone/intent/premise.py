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
  exists: "already", "existing", "reuse/build on/on top of", "the … helper, flag, setting …",
  or a request to switch a named setting on ("enable", "turn/switch … on", "set").
* **Never an API the request adopts.** "Use `Decimal`", "call `logger.warning`", "use
  `structuredClone`": telling the agent to use or call a name is how a request brings in the
  standard library's, the runtime's or a dependency's API, which no repository defines.
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
  ``GITHUB_*``, ``DEBUG``, ``NO_COLOR``…) never get a note. Nor does a ``--flag`` in a
  sentence that names the program it belongs to ("the `--cov` flag … pytest-cov", "when
  running node --test"), unless the request says the behaviour works today.
* **External things are skipped:** URLs, package specs (``@scope/pkg``, ``node:fs``), HTTP
  headers, versions, dates, numbers.
* Silent while the index is not built, and once per name per session (the caller keeps that).
"""

from __future__ import annotations

import builtins
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
# The deny for the first file edit after a note (T4): a careful agent can read the note and
# still edit first; the user hears about the missing behaviour before anything is built on it.
HOLD = (
    "Truthstone: before editing: the request assumes {what} (see the note above). First tell the user "
    "so in a message ({say}); then continue only if the change still makes sense."
)


def hold_finding(text: str) -> Finding:
    """The record of a held first edit: the premise note's kind, at the edit."""
    return Finding(
        category=ChallengeCategory.ASSUMPTION,
        verdict=Verdict.CONTRADICTED,
        failure_mode=FailureMode.CONTINUED_ON_BAD_ASSUMPTION,
        severity=Severity.MEDIUM,
        subject=SUBJECT,
        summary="the first edit after a premise note, held once so the user hears first",
        detail=text,
        level=EscalationLevel.REPOSITORY,
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
#
# Not "use", "call", "invoke" or "via" on their own: that is how a request tells the agent to
# adopt an API — the standard library's, the runtime's, a dependency's ("use `Decimal`", "call
# `logger.warning`", "use `structuredClone`") — and no repository defines those. A request that
# rests on the repository having a name says so: "the existing X", "already", "reuse X",
# "build it on X", "the X helper" (audit of 66e1617: 14 of 46 ordinary requests were noted).
_EXISTS_NEAR = re.compile(
    r"\b(?:already|existing|current|reuse|reuses|"
    r"enable|on top of|based on|build (?:it |this |that )?(?:on|upon))\b",
    re.IGNORECASE,
)
# Absence, in the words just before a name: the request says it is NOT there ("the existing
# route ignores `offset`", "currently has no `updated_at` field", "lacks `customerId`") — the
# name is what the request adds, not a premise (audit of 66e1617, R3-4). `_WORD` keeps letters
# only, so "doesn't" reads as "doesn".
_ABSENT = re.compile(
    r"\b(?:ignor(?:e|es|ed|ing)|lacks?|lacking|missing|no|without|not|never|doesn|don|isn|aren|"
    r"hasn|haven|wasn|weren|neither|nor)\b",
    re.IGNORECASE,
)
# A sentence that names the program a flag belongs to: "the `--cov` flag ... pytest-cov",
# "when running node --test". That flag is the tool's switch, not the project's.
_TOOL_NAMED = re.compile(
    r"\b(?:pytest(?:-cov)?|py\.test|coverage|tox|nox|pipx?|uvx?|poetry|pdm|hatch|ruff|black|isort|"
    r"flake8|pylint|mypy|pyright|npm|npx|yarn|pnpm|tsc|tsx|ts-node|jest|vitest|mocha|eslint|"
    r"prettier|webpack|vite|esbuild|rollup|babel|git|gh|docker(?:-compose)?|kubectl|helm|terraform|"
    r"cargo|rustc|mvn|gradle|dotnet|curl|wget|rsync)\b"
    r"|\b(?:node|deno|bun|python3?)\s+(?:-m\s+\w|--?[a-z])"
    r"|\bgo\s+(?:test|build|run|vet|mod)\b|\bmake\s+(?:check|test|lint|build|all|install|ci)\b",
    re.IGNORECASE,
)
# A kind noun after the name: "the X helper", "the --foo flag".
_KIND_NOUN = re.compile(
    r"\s*[`)]?\s*(?:helper|function|method|class|module|flag|option|switch|setting|key|"
    r"variable|env(?:ironment)? var(?:iable)?|config|command|subcommand)s?\b",
    re.IGNORECASE,
)
_SETTING_NOUN = re.compile(
    r"\b(?:option|switch|setting|key|config|variable|env(?:ironment)? var(?:iable)?)s?\b", re.IGNORECASE
)
# Where a sentence moves from what is to what should be: "…; it should …", "…: …", "… but
# must …". An existence word speaks for its own clause only, so the names of the requested
# change ("…currently retries 3 times; it should honour `max_retries`") are not asserted.
_CLAUSE_BREAK = re.compile(
    r"[;:](?=\s)|\s[\u2014\u2013]\s|\s--\s|\b(?:but|should(?!\s+already)|must|needs?\s+to|has\s+to|have\s+to)\b",
    re.IGNORECASE,
)
# "… when X=1 is set: turn that on" — a switch-on phrase points back across the sentence.
_SWITCH_ON = re.compile(
    r"\b(?:switch|switches|switching|turn|turns|turning|flip|flipping)\b[^.?!\n]{0,40}?\bon\b",
    re.IGNORECASE,
)
# The language's own names, which no repository defines: Python's builtins and the globals of
# JavaScript and its runtimes. ("`NaN`", "`Date` values", "returns `None`", "with `print`".)
_LANGUAGE_NAMES = frozenset(n for n in dir(builtins) if not n.startswith("_")) | frozenset(
    {
        "Array", "ArrayBuffer", "BigInt", "Boolean", "Buffer", "DataView", "Date", "Error",
        "EvalError", "Function", "Infinity", "Intl", "JSON", "Map", "Math", "NaN", "Number",
        "Object", "Promise", "Proxy", "RangeError", "ReferenceError", "Reflect", "RegExp", "Set",
        "String", "Symbol", "SyntaxError", "TypeError", "URIError", "URL", "URLSearchParams",
        "WeakMap", "WeakRef", "WeakSet", "AbortController", "TextDecoder", "TextEncoder",
        "console", "structuredClone", "fetch", "process", "queueMicrotask",
        "setTimeout", "setInterval", "clearTimeout", "clearInterval", "undefined", "null",
        "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent",
    }
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

    @property
    def hold(self) -> str:
        """The deny for the task's first file edit (T4): the note may have gone unheeded."""
        clauses, says = [], []
        for a in self.missing[:3]:
            files = self.only_in.get(a.name)
            if files:
                listed = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
                clauses.append(
                    f"`{a.name}`, but it appears only in {listed}, and no code in this repository reads it"
                )
                says.append(f"nothing in this repository reads `{a.name}`")
            else:
                clauses.append(f"`{a.name}`, but it appears nowhere in this repository")
                says.append(f"`{a.name}` doesn't exist in this repository")
        if not clauses:
            return ""
        # The fact to state, in so many words: the user hears it before anything is built on it.
        return HOLD.format(what="; and ".join(clauses), say='e.g. "' + "; ".join(says) + '"')

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
    """Things a repository does not define: URLs, package specs, headers, versions, dates, and
    the language's own names (Python's builtins, the JavaScript globals)."""
    lowered = name.lower()
    head = name.removesuffix("()").partition(".")[0]
    return (
        "://" in name
        or lowered.startswith(("www.", "node:", "@", "x-", "http"))
        or re.fullmatch(r"v?\d+(?:[.\-/]\d+)*\w*", name) is not None
        or (re.fullmatch(r"[A-Z/:\-]+", name) is not None and not _ENV.fullmatch(name))
        or head in _LANGUAGE_NAMES
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
        if re.fullmatch(r"[A-Za-z_][\w-]*", inner) and len(inner) >= 3 and not _WELL_KNOWN_ENV.match(inner):
            put(m.start(1), Assertion(inner, "name", (inner,)))
    return sorted(found.values(), key=lambda item: item[0])


def _clause(sentence: str, offset: int, length: int) -> str:
    """The clause of ``sentence`` the name at ``offset`` sits in (``_CLAUSE_BREAK``). A modal
    starts the clause it introduces: "…; it should honour `max_retries`" puts the name with
    "should", not with what came before."""
    start, end = 0, len(sentence)
    for match in _CLAUSE_BREAK.finditer(sentence):
        if match.end() <= offset:
            start = match.start()
        elif match.start() >= offset + length:
            end = match.start()
            break
    return sentence[start:end]


def _clause_start(sentence: str, offset: int) -> int:
    """Where the clause holding ``offset`` begins (see :func:`_clause`)."""
    start = 0
    for match in _CLAUSE_BREAK.finditer(sentence):
        if match.end() > offset:
            break
        start = match.start()
    return start


def _window(before: str) -> str:
    return " ".join(_WORD.findall(before)[-4:])


# A file of the project's own configuration the request names ("in app.toml", "to
# config/rates.json"). A tool's (tsconfig, package.json, pyproject, lint and test-runner
# configs: `_TOOL_OWNED`) is not the project's.
_CONFIG_FILE = re.compile(
    r"(?<![\w@/.-])((?:[\w.-]+/)*[\w.-]*\.(?:toml|json|jsonc|ya?ml|ini|cfg|conf|env|properties))(?![\w/-])",
    re.IGNORECASE,
)
# A clause that conditions present behaviour on a name: "… appends one when `x = true` is set".
_CONDITION = re.compile(r"\b(?:when|whenever|if|once)\b", re.IGNORECASE)
# A request that builds the behaviour: then a key it names is the plan, not a premise.
_BUILDS = re.compile(
    r"\b(?:implement\w*|introduc\w*|add\s+support|support\s+for|should|must|needs?\s+to|has\s+to|"
    r"have\s+to|new|build\w*|teach|wire\s+up|hook\s+up|make\s+(?:it|sure))\b",
    re.IGNORECASE,
)


def _named_for_project_config(prompt: str, sentence: str, offset: int) -> bool:
    """A key the request ties to a file of the project's own configuration, in a clause that
    says what the project does when it is set: "the report gets a summary line when `summary =
    true` is under [report] in app.toml: switch it on". Such a request asserts that the
    project reads the key, with "already" or without, so a key the repository has nowhere is
    a false premise. Never a tool's configuration (its keys are the tool's: tsconfig,
    package.json, pyproject, lint and test-runner configs), and never in a request that builds
    the behaviour ("should", "implement", "new" ...)."""
    files = [match.group(1) for match in _CONFIG_FILE.finditer(sentence)]
    if not files or any(_tool_owned(path) for path in files):
        return False
    lead = sentence[_clause_start(sentence, offset) : offset]
    if not _CONDITION.search(lead[-160:]):
        return False
    return _BUILDS.search(prompt) is None


def _asserted(
    sentence: str, offset: int, name: str, kind: str = "name", prompt: str | None = None
) -> bool:
    """Whether this sentence asserts that ``name`` (at ``offset``) is already there.

    Switching a setting on ("enable X", "turn X on") asserts only an environment switch — the
    shape of a premise about behaviour behind a named switch. Any other name a request switches
    on is an option it adds, almost always a tool's (`strictNullChecks`, an eslint rule, a mypy
    or pytest setting), which no repository defines until the change is made (audit of 66e1617:
    12 of 22 ordinary enable/turn-on requests were noted). With "already", "existing",
    "currently" or "is supposed to" the request does say the behaviour exists, for any name.
    """
    before = sentence[:offset]
    after = sentence[offset + len(name) :]
    clause = _clause(sentence, offset, len(name))
    # The words just before the name, within its own clause: "src/x.ts already has `a`; add
    # `b`" must not lend `a`'s "already" to `b` (audit of 66e1617).
    window = _window(before[_clause_start(sentence, offset) :])
    if re.search(r"\b(?:already|existing)\b", window, re.IGNORECASE):
        return True  # "on top of the existing X": nearest word wins
    if name.startswith("--"):
        # A flag is the project's only when the request calls it that ("the --dry-run flag")
        # or says it exists ("already", "existing"); "use --soft" names a tool's own flag.
        named = _KIND_NOUN.match(after) and re.search(r"\b(?:the|our|its)\s+\S*$", before, re.IGNORECASE)
        return bool(named) or _EXISTING_BEHAVIOUR.search(sentence) is not None
    # Creation binds tighter than the sentence: a creating word within the four words before.
    if _CREATES.search(window):
        return False
    if _ABSENT.search(window):
        return False  # "the route ignores `offset`", "has no `updated_at`": said not to be there
    near = {match.lower() for match in _EXISTS_NEAR.findall(window)}
    if near - {"enable"} or (near and kind == "env"):
        return True
    if _CREATING_SENTENCE.search(sentence):
        return False
    noun = _KIND_NOUN.match(after)
    if noun and re.search(r"\b(?:the|our|its|their|your)\s+\S*$", before, re.IGNORECASE):
        # "the X helper", "the --foo flag": the project's own. "the X setting / option" is
        # as often a tool's (GitHub's `concurrency` setting, a compiler option), and "the X
        # environment variable" is how a request introduces one ("read the timeout from the
        # `X` environment variable"): those assert themselves only with an existing-behaviour
        # word in their clause ("the existing X setting", "X already …").
        if not _SETTING_NOUN.search(noun.group(0)):
            return True
        return _EXISTING_BEHAVIOUR.search(clause) is not None
    if _EXISTING_BEHAVIOUR.search(clause):
        return True  # "X currently …", "the X setting is supposed to …": in X's own clause
    if kind in ("name", "env") and _named_for_project_config(prompt or sentence, sentence, offset):
        return True  # "… appends one when `x = true` is under [export] in app.toml: switch it on"
    return kind == "env" and _SWITCH_ON.search(sentence) is not None


def assertions(prompt: str) -> list[Assertion]:
    """The names a prompt asserts exist, in order, without names it asks to create."""
    created: set[str] = set()
    out: dict[str, Assertion] = {}
    for _start, sentence in _sentences(prompt or ""):
        existing = _EXISTING_BEHAVIOUR.search(sentence) is not None
        tool_named = _TOOL_NAMED.search(sentence) is not None
        for offset, candidate in _candidates(sentence):
            if candidate.kind == "flag" and tool_named and not existing:
                continue  # another program's switch, unless the request says it works today
            if _asserted(sentence, offset, candidate.name, candidate.kind, prompt):
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

# Configuration the repository index skips: its top-level dot-files and its CI and tool
# directories. Without them a name defined only in `.eslintrc.json`, `.prettierrc`,
# `.env.example` or a workflow read as "appears nowhere" (audit of 66e1617).
_DOT_DIRS = frozenset({".github", ".circleci", ".gitlab", ".husky", ".devcontainer", ".vscode"})
# A real `.env` holds secrets: never read. Its documented templates are configuration.
_REAL_ENV = re.compile(r"^\.env(?:\.(?!(?:example|sample|template|dist|defaults)$)[\w.-]+)?$", re.IGNORECASE)
MAX_DOT_FILES = 200


def dot_config_files(root: Path) -> list[str]:
    """The dot-files the index does not list: ``root``'s own (``.eslintrc.json``,
    ``.env.example`` …, never ``.env``) and those under ``.github/`` and the like. Bounded;
    never raises."""
    out: list[str] = []
    try:
        for entry in sorted(root.iterdir()):
            name = entry.name
            if not name.startswith(".") or name in (".git", ".hg", ".svn"):
                continue
            if entry.is_file() and not _REAL_ENV.match(name):
                out.append(name)
            elif entry.is_dir() and name in _DOT_DIRS:
                for path in sorted(entry.rglob("*")):
                    if len(out) >= MAX_DOT_FILES:
                        return out
                    if path.is_file():
                        out.append(path.relative_to(root).as_posix())
            if len(out) >= MAX_DOT_FILES:
                break
    except OSError:
        pass
    return out


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
    files += [rel for rel in dot_config_files(root) if rel not in present]
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
    env_keys = {a.keys[0] for a in unresolved if a.kind == "env"}
    from truthstone.validate import config_reads  # here: validate's package imports the engine's world

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
        if code and env_keys - found:
            # A settings class, a computed key, the whole environment: read, though not spelled.
            found |= config_reads.indirect_reads(text, env_keys - found)
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
