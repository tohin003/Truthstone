"""A false premise still unmet at "done" (day 3; the Stop half of (d)).

The failure class
-----------------
The request says a named thing already works: "the client already logs every call when you
pass ``traceCalls: true``; switch that on in the wrapper". The prompt-time note
(``intent/premise.py``) found the name nowhere. The agent tells the user, then does the job
another way (it logs in the wrapper and never adds ``traceCalls``) and reports done. The user
still believes in a switch that does not exist, and everything that relies on it, the
request's own statement included, stays false. The same holds for a key set in configuration
that no code reads; ``validate/config_reads.py`` says that one when the change is
configuration only, and this check then stays quiet about the same names (the arbiter's
``_without_repeats``).

What is checked, deterministically
----------------------------------
Only in a task whose prompt got a premise note: its names (``TaskSpec.premises``), stored with
the task. At a Stop each is resolved again against the repository as it is now. A name is
still unmet unless some **non-test code** file **reads** it:

* a member access (``options.traceCalls``, ``cfg?.trace_calls``), a key looked up by string
  (``get("trace_calls")``, ``env["TRACE_CALLS"]``), or the bare name in an expression (a
  parameter or variable used in a body);
* not where it is only written or passed along: an object-literal key or a type member
  (``{ traceCalls: true }``, ``traceCalls?: boolean``), a keyword argument, a parameter
  default or an assignment (``trace_calls=True``, ``x.trace_calls = 1``), a quoted dictionary
  key, a declaration or an import.

Test files never count: a test that passes the switch does not implement it. A tool's own
configuration counts as read (the tool reads it), and so does an environment variable a code
file reads without spelling it (``config_reads.indirect_reads``). Comments count for nothing.
A switch the request says another program reads (a dependency, a command the configuration
runs), a variable a runtime or a tool reads, or a ``--flag`` (as often a runtime's or a tool's
as the project's) is never checked here; the prompt-time note and the hold still speak.
A path the request named is met when it exists. Code in languages other than Python and
JS/TS: any occurrence outside a line comment counts (precision first).

It speaks on a completion claim, once per task (``premise_unmet``). No note, no finding at
all: a task whose prompt was never noted is never even looked at, so control tasks cannot
carry one. A scan that would read more than ``MAX_SCAN_BYTES`` says nothing.
"""

from __future__ import annotations

import io
import keyword
import logging
import re
import tokenize
from pathlib import Path

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.intent import premise
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex

log = logging.getLogger(__name__)

__all__ = ["concerns", "reads"]

MAX_FILE_BYTES = 1_000_000
MAX_SCAN_BYTES = 64_000_000
_JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte")


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The premise-unmet concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    names = [name for name in dict.fromkeys(state.spec.premises or []) if name]
    if not names:
        return []  # no note, no finding (T4b: control tasks never carry one)
    from truthstone.validate import config_reads
    from truthstone.verify import arbiter

    prompt = state.spec.prompt or ""
    texts = [after for _, after in arbiter.changed_texts(state, index).values() if after]
    external = config_reads.external_programs(index, texts)
    asserted = {a.name: a for a in premise.assertions(prompt)}
    # A `--flag` is as often a runtime's or a tool's as the project's: the note and the hold speak
    # for it, this check does not.
    names = [
        name
        for name in names
        if not _another_programs(prompt, name, external)
        and (asserted[name].kind if name in asserted else "name") != "flag"
    ]
    if not names:
        return []
    wanted = {
        name: asserted.get(name) or premise.Assertion(name, "name", (name.removesuffix("()"),))
        for name in names
    }
    root = Path(index.root)
    unmet = _unmet(root, _files(index, state), wanted)
    if not unmet:
        return []
    shown = list(unmet)[:3]
    listing = " and ".join(f"`{name}`" for name in shown)
    facts = []
    for name in shown:
        where = sorted(unmet[name])
        if where:
            files = ", ".join(where[:3]) + (f" and {len(where) - 3} more" if len(where) > 3 else "")
            facts.append(f"`{name}` is only set or passed along ({files}), never read")
        elif wanted[name].kind == "path":
            facts.append(f"`{name}` does not exist")
        else:
            facts.append(f"`{name}` appears in no code")
    text = (
        f"The request says {listing} already {'works' if len(shown) == 1 else 'work'}, and still no code "
        f"in this repository reads {'it' if len(shown) == 1 else 'them'}: {'; '.join(facts)}. Finishing "
        f"as done tells the user {listing} {'works' if len(shown) == 1 else 'work'}; that is not true yet."
    )
    finding = arbiter.finding(
        ReasonCategory.PREMISE_UNMET,
        Severity.MEDIUM,
        summary=f"the request's premise is still unmet: {', '.join(shown)}",
        detail="; ".join(facts),
        evidence=[
            EvidenceRef(source="filesystem", symbol=name, note="; ".join(unmet[name][:3])) for name in shown
        ],
        mode=FailureMode.FALSE_COMPLETION,
    )
    return [arbiter.Concern(ReasonCategory.PREMISE_UNMET, text, finding)]


def _another_programs(prompt: str, name: str, external: frozenset[str]) -> bool:
    """The request says another program does the work behind ``name`` (a dependency, a command
    the configuration runs: "the server already reads `X_TIMEOUT`"), or ``name`` is a variable a
    runtime or a tool reads: that program's switch, not this repository's (audit R2-6)."""
    from truthstone.validate import config_reads

    if config_reads.is_well_known(name):
        return True
    claimed = config_reads.claimed_to_work(prompt, name)
    return claimed and not config_reads.claimed_to_work(prompt, name, external)


def _files(index: RepoIndex, state: TaskState) -> list[str]:
    files = list(index.files)
    known = set(files)
    return files + sorted(path for path in state.touched_files if path not in known)


def _unmet(root: Path, files: list[str], wanted: dict[str, premise.Assertion]) -> dict[str, list[str]]:
    """name -> the non-test code files that only write or pass it ([] for none), for the names
    no code reads (a path: one that does not exist). Empty when the scan would cost more than its
    budget: silence."""
    from truthstone.validate import config_reads

    missing_paths: dict[str, list[str]] = {}
    keys: dict[str, list[str]] = {}
    for name, assertion in wanted.items():
        if assertion.kind == "path":
            path = assertion.keys[0].removeprefix("./").rstrip("/")
            present = path in files or any(p.startswith(path + "/") for p in files) or (root / path).exists()
            if not present:
                missing_paths[name] = []
        else:
            keys[name] = [key for key in assertion.keys if key]
    unread: dict[str, list[str]] = {name: [] for name in keys}
    budget = MAX_SCAN_BYTES
    for rel in files:
        if not unread:
            break
        if scanner.is_test_path(rel) or not (premise._code_file(rel) or premise._tool_owned(rel)):
            continue
        try:
            full = root / rel
            size = full.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            budget -= size
            if budget < 0:
                return {}  # too big to be sure: say nothing
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name in list(unread):
            present = [key for key in keys[name] if key in text]
            if not present:
                continue
            if premise._tool_owned(rel) or any(reads(text, key, rel) for key in present):
                del unread[name]  # read here (a tool reads its own configuration)
            elif wanted[name].kind == "env" and config_reads.indirect_reads(text, set(present)):
                del unread[name]  # the whole environment, a computed key, a settings class
            else:
                unread[name].append(rel)  # only written or passed along here
    found = {**missing_paths, **unread}
    return {name: found[name] for name in wanted if name in found}


# -- reading, not passing along -----------------------------------------------------------------


def reads(text: str, key: str, path: str) -> bool:
    """Whether the code ``text`` (of file ``path``) reads ``key`` somewhere, rather than only
    writing or passing it along (see the module doc). Never raises."""
    try:
        if path.lower().endswith((".py", ".pyi")):
            return _python_reads(text, key)
        if path.lower().endswith(_JS):
            return _js_reads(text, key)
    except Exception:  # unreadable code: an occurrence counts (precision first)
        log.debug("truthstone: could not classify the reads of %s in %s", key, path, exc_info=True)
        return re.search(rf"(?<![\w$-]){re.escape(key)}(?![\w$-])", text) is not None
    # Another language: an occurrence outside a line comment counts.
    pattern = re.compile(rf"(?<![\w$-]){re.escape(key)}(?![\w$-])")
    return any(
        pattern.search(line.split("#", 1)[0].split("//", 1)[0]) for line in text.splitlines() if key in line
    )


_PY_DECLARES = frozenset({"def", "class", "import", "from", "global", "nonlocal", "as", "lambda"})


def _python_reads(text: str, key: str) -> bool:
    tokens = [
        token
        for token in tokenize.generate_tokens(io.StringIO(text).readline)
        if token.type not in (tokenize.COMMENT, tokenize.NL)
    ]
    line_start = True
    params = 0  # >0 inside a `def`'s parameter list: its names are declared there, not read
    expecting_params = False
    for n, token in enumerate(tokens):
        previous = tokens[n - 1] if n else None
        following = tokens[n + 1] if n + 1 < len(tokens) else None
        after = tokens[n + 2] if n + 2 < len(tokens) else None
        if token.type == tokenize.NAME and token.string == "def":
            expecting_params = True
        elif token.type == tokenize.OP and token.string in "([{":
            if expecting_params and token.string == "(" and params == 0:
                params, expecting_params = 1, False
            elif params:
                params += 1
        elif token.type == tokenize.OP and token.string in ")]}" and params:
            params -= 1
        if token.type == tokenize.NAME and token.string == key and not keyword.iskeyword(key):
            if previous is not None and previous.string in _PY_DECLARES:
                pass  # `def key`, `import key`, `as key`: a declaration
            elif params == 1 and previous is not None and previous.string in ("(", ",", "*", "**"):
                pass  # a parameter: declared here, read (or not) in the body
            elif following is not None and following.string == "=":
                pass  # an assignment, a keyword argument or a parameter default: a write
            elif following is not None and following.string == ":" and line_start:
                pass  # an annotation: `key: bool = False`
            else:
                return True
        elif token.type == tokenize.STRING and _py_string(token.string) == key:
            if following is not None and following.string == ":":
                pass  # `{"key": value}`: a key written
            elif (
                following is not None
                and following.string == "]"
                and after is not None
                and after.string == "="
            ):
                pass  # `config["key"] = value`
            else:
                return True  # `get("key")`, `env["KEY"]`, `getattr(obj, "key")`
        line_start = token.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
    return False


def _py_string(literal: str) -> str | None:
    match = re.fullmatch(r"(?i)[rbuf]{0,2}(['\"]{1,3})(.*)\1", literal, re.DOTALL)
    return match.group(2) if match else None


def _js_reads(text: str, key: str) -> bool:
    from truthstone.validate import weakened_tests

    blank, kept = weakened_tests._js_scan(text)
    word = re.compile(rf"(?<![\w$]){re.escape(key)}(?![\w$])")
    for match in word.finditer(blank):
        start, end = match.span()
        before = blank[max(0, start - 40) : start]
        after = blank[end : end + 40]
        if re.search(r"(?:\?\.|\.)\s*$", before):
            if not re.match(r"\s*=(?![=>])", after):
                return True  # `options.key`, `opts?.key`: read (not `options.key = …`)
            continue
        if re.search(
            r"(?:^|[^\w$])(?:function|class|interface|type|enum|let|const|var|import|export|as)\s+$", before
        ):
            continue  # a declaration of the name
        if re.match(r"\s*\??\s*:", after) and not re.search(r"(?:\?|\bcase)\s*$", before):
            continue  # `{ key: true }`, `key?: boolean`: written or declared, not read
        if re.match(r"\s*=(?![=>])", after):
            continue  # an assignment or a default
        if _js_import(blank, start, end):
            continue
        return True  # a bare use: `if (key)`, `{ key }` handed on, `key && …`
    quoted = re.compile(rf"(['\"`]){re.escape(key)}\1")
    for match in quoted.finditer(kept):
        after = kept[match.end() : match.end() + 40]
        if re.match(r"\s*:", after) or re.match(r"\s*\]\s*=(?![=>])", after):
            continue  # `{"key": 1}`, `config["key"] = 1`
        return True  # `get("key")`, `env["KEY"]`
    return False


def _js_import(blank: str, start: int, end: int) -> bool:
    """Whether the name at ``start:end`` sits in an import or re-export list
    (``import { a, key } from "m"``)."""
    opening, closing = blank.rfind("{", 0, start), blank.find("}", end)
    if opening < 0 or closing < 0 or re.search(r"[{}();=]", blank[opening + 1 : start] + blank[end:closing]):
        return False
    return bool(
        re.search(r"\b(?:import|export)\s+(?:type\s+)?$", blank[max(0, opening - 30) : opening])
        and re.match(r"\s*from\b", blank[closing + 1 : closing + 40])
    )
