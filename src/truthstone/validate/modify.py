"""MODIFY: rewriting a proposed action, under a narrowing invariant (SPEC §18).

`updatedInput` lets Truthstone rewrite a tool's arguments before it runs. That is a real
capability and a real hazard: a host may run the rewritten call without the developer
seeing the original, and the Codex adapter shows the guarded form to the agent as "re-issue
it in this guarded form". An unsound rewrite is therefore an active hazard, not a no-op.

The decision to allow it rests on one property: **the rewrite is a narrowing.** The host
LLM proposed the action; Truthstone only ever makes it reach less far. This module makes
that property something the code proves rather than something the design assumes.

Rules, in order of importance:

1. **Judge the original first.** The risk checks run on the command as written. A rewrite
   is only considered when the *only* high or critical finding is the unvalidated-variable
   delete that the rewrite guards (IMPROVEMENTS.md A5). Anything else is the developer's
   call, so it goes to them — with the guarded form as a suggestion when one is sound.
2. **Never broaden, never change meaning.** No rewrite when the guard would be meaningless
   or would alter what runs:
   - the variable is one a shell always sets (`rm -rf $HOME` still deletes home once
     "guarded" — the probe that found this is in A5);
   - a parameter expansion is involved (`${OUT:-/tmp/x}` became invalid shell);
   - more than one variable is deleted (`rm -rf $A $B/` left `$B` unguarded);
   - the variable was given a value with whitespace earlier in the command (quoting
     `DIRS="dist build"; rm -rf $DIRS` turns two deletes into one of a missing path);
   - the delete sits where a prefixed guard changes control flow (after `||`, in a pipe).
3. **Re-check the result.** The rewritten arguments go back through the risk checks and
   must have no high or critical finding left.
4. **Never silent.** Every rewrite announces what changed, why, and the guarded command.

Anything that fails a rule is not rewritten — it is escalated, which is always safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from truthstone.core.enums import (
    ChallengeCategory,
    EscalationLevel,
    FailureMode,
    Severity,
    Verdict,
)
from truthstone.core.events import AgentEvent
from truthstone.core.models import EvidenceRef, Finding
from truthstone.validate import checks, shell

# Variables a shell or login session virtually always sets. A guard against them being
# empty guards nothing (A5: `[ -n "$HOME" ] && rm -rf "$HOME"` still deletes home).
ALWAYS_SET: frozenset[str] = frozenset(
    {
        "HOME", "PWD", "OLDPWD", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "HOSTNAME",
        "HOSTTYPE", "OSTYPE", "MACHTYPE", "LANG", "TERM", "UID", "EUID", "PPID", "SHLVL",
        "IFS", "RANDOM", "SECONDS", "LINENO", "BASH", "BASH_VERSION", "BASHPID", "PS4",
        "GROUPS",
    }
)

_SERIOUS = (Severity.HIGH, Severity.CRITICAL)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.S)
_DECLARERS = frozenset({"export", "local", "declare", "typeset", "readonly"})
# Words that may stand before `rm` in the same simple command, without options. A guard
# placed before the whole command still tests what `rm` will receive.
_PREFIXES = frozenset({"sudo", "nohup", "time", "command", "nice"})
_MKTEMP = re.compile(r"\$\(\s*mktemp\b[^()`]*\)|`\s*mktemp\b[^`]*`")
_REDIRECT = re.compile(r"\d*(>>?|<|&>|>&)\S*")
# Where `[ -n "$X" ] && ` can be put in front of a command without changing when the
# command runs. Not after `||` (`a || [ -n "$X" ] && rm` runs `rm` when `a` succeeds), not
# in a pipe, and not before `||` (the fallback would start running when the guard fails).
_GUARDABLE = frozenset({"", ";", "&", "\n", "&&"})


@dataclass(slots=True)
class Rewrite:
    arguments: dict
    summary: str  # what changed, in one line
    reason: str  # why it is safe
    guarded: str = ""  # the rewritten command, as it will run


@dataclass(slots=True)
class _Ref:
    kind: str  # "simple", "expansion", "special" or "substitution"
    name: str
    start: int
    end: int
    quoted: bool  # inside double quotes already


@dataclass(slots=True)
class _Analysis:
    variables: list[str] = field(default_factory=list)  # distinct, in order
    blockers: list[str] = field(default_factory=list)  # why no guard is sound
    guarded: str = ""  # the command with every rm-target variable guarded and quoted


def propose(event: AgentEvent, findings: list[Finding] | None = None) -> Rewrite | None:
    """A safe narrowing of this action, or None.

    `findings` are the risk checks' findings on the *original* command; computed here when
    not given. Returning None is always acceptable — the action is then judged as-is.
    """
    command = _command(event)
    if command is None:
        return None
    if findings is None:
        findings = checks.risky_command(event)

    # (a) The one serious problem must be the one the rewrite fixes.
    serious = [f for f in findings if f.severity in _SERIOUS]
    if len(serious) != 1 or not checks.is_variable_delete(serious[0]):
        return None

    analysis = _analyse(command)
    # (b) always-set, (c) expansion, (e) word splitting, structure — and (d) one variable.
    if analysis is None or analysis.blockers or len(analysis.variables) != 1:
        return None

    rewritten = analysis.guarded
    candidate = dict(event.arguments)
    candidate["command"] = rewritten
    # (f) the result must itself be clean.
    if not _is_narrowing(command, rewritten) or not _still_safe(event, candidate):
        return None

    name = analysis.variables[0]
    return Rewrite(
        arguments=candidate,
        summary=f"guarded `{name}` against being unset",
        reason=(
            f"`rm -rf ${name}` deletes `/` if `{name}` is empty. The rewrite refuses to run "
            "rather than expanding to a root path; it can only ever affect what the command "
            "already named."
        ),
        guarded=rewritten,
    )


def safer_form(event: AgentEvent, findings: list[Finding] | None = None) -> str | None:
    """The guarded form to *suggest* in a review request, when one is sound.

    Offered where the guard itself is sound but an automatic rewrite was refused for
    another reason — other serious findings in the same command, or several variables.
    Never where the guard would be meaningless or change meaning (always-set variables,
    parameter expansions, word-split values): a suggestion that still deletes home is
    worse than none.
    """
    command = _command(event)
    if command is None:
        return None
    if findings is None:
        findings = checks.risky_command(event)
    if not any(checks.is_variable_delete(f) for f in findings):
        return None
    analysis = _analyse(command)
    if analysis is None or analysis.blockers or analysis.guarded == command:
        return None
    return analysis.guarded


def _command(event: AgentEvent) -> str | None:
    if event.tool != "Bash":
        return None
    command = event.arg("command")
    if not isinstance(command, str) or not command.strip():
        return None
    return command


# -- analysis -------------------------------------------------------------------------


def _analyse(command: str) -> _Analysis | None:
    """Every recursive `rm` whose targets name a variable, and how to guard them.

    None when the command has no such `rm` — or when it is too long to rewrite in full.
    """
    split = shell.split(command)
    if split.truncated:
        return None
    analysis = _Analysis()
    edits: list[tuple[int, int, str]] = []
    first_rm: int | None = None
    seen: set[str] = set()

    for position, piece in enumerate(split.pieces):
        words = shell.words(piece.text)
        at = _rm_at(words)
        if at is None:
            continue
        options, targets = _rm_arguments(words[at + 1 :])
        if not _recursive(options):
            continue
        referenced: list[tuple[shell.Word, list[_Ref]]] = []
        names: list[str] = []
        for word in targets:
            refs = _refs(word.raw)
            if not refs:
                continue
            referenced.append((word, refs))
            for ref in refs:
                if ref.kind == "simple":
                    names.append(ref.name)
                elif ref.kind == "expansion":
                    analysis.blockers.append("a parameter expansion (`${VAR:-…}` and the like)")
                else:
                    analysis.blockers.append("a positional parameter or a command substitution")
        if not referenced:
            continue
        if first_rm is None:
            first_rm = position
        if piece.opaque or piece.before not in _GUARDABLE or piece.after not in _GUARDABLE:
            analysis.blockers.append("where the delete sits in the command line")
        names = list(dict.fromkeys(names))
        for name in names:
            if name not in seen:
                seen.add(name)
                analysis.variables.append(name)
        guard = " && ".join(f'[ -n "${name}" ]' for name in names)
        text = _splice(piece.text, [(w.start, w.end, _quoted(w.raw, refs)) for w, refs in referenced])
        edits.append((piece.start, piece.end, f"{guard} && {text}" if guard else text))

    if first_rm is None:
        return None
    split_names = _split_by_assignment(split.pieces[:first_rm])
    for name in analysis.variables:
        if name in ALWAYS_SET:
            analysis.blockers.append(f"`{name}` is always set, so a guard against it being empty is void")
        elif name in split_names:
            analysis.blockers.append(f"`{name}` holds several words, which quoting would join")
    analysis.blockers = list(dict.fromkeys(analysis.blockers))
    analysis.guarded = _splice(command, edits)
    return analysis


def _splice(text: str, edits: list[tuple[int, int, str]]) -> str:
    """`text` with each (start, end, replacement) applied, in one pass (edits in order)."""
    out: list[str] = []
    last = 0
    for start, end, replacement in edits:
        out.append(text[last:start])
        out.append(replacement)
        last = end
    out.append(text[last:])
    return "".join(out)


def _unquoted(word: str) -> str:
    if len(word) >= 2 and word[0] == word[-1] and word[0] in ("'", '"'):
        return word[1:-1]
    return word


def _rm_at(words: list[shell.Word]) -> int | None:
    """The index of `rm` in command position: after assignments and option-less prefixes."""
    for index, word in enumerate(words):
        raw = word.raw
        if _ASSIGNMENT.fullmatch(raw):
            continue
        name = _unquoted(raw).rsplit("/", 1)[-1]
        if name == "rm":
            return index
        if raw in _PREFIXES:
            continue
        return None
    return None


def _rm_arguments(args: list[shell.Word]) -> tuple[list[str], list[shell.Word]]:
    """(option words, target words) of an `rm`, redirections set aside."""
    options: list[str] = []
    targets: list[shell.Word] = []
    ended = False
    skip = False
    for word in args:
        raw = word.raw
        if skip:
            skip = False
            continue
        if _REDIRECT.fullmatch(raw):
            # A bare operator (`2>`, `>`) takes the next word as its target.
            skip = raw.lstrip("0123456789") in (">", ">>", "<", "&>", ">&")
            continue
        if not ended and raw == "--":
            ended = True
            continue
        if not ended and raw.startswith("-") and len(raw) > 1:
            options.append(raw)
            continue
        targets.append(word)
    return options, targets


def _recursive(options: list[str]) -> bool:
    return any(
        option == "--recursive" or (not option.startswith("--") and ("r" in option or "R" in option))
        for option in options
    )


def _refs(raw: str) -> list[_Ref]:
    """The `$` references in one word that the shell would expand (not in single quotes)."""
    refs: list[_Ref] = []
    i, n = 0, len(raw)
    quote: str | None = None
    while i < n:
        c = raw[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == '"':
            quote = None if quote == '"' else '"'
            i += 1
            continue
        if c == "'" and quote is None:
            quote = "'"
            i += 1
            continue
        if c == "`":
            refs.append(_Ref("substitution", "", i, n, quote == '"'))
            return refs
        if c != "$" or i + 1 >= n:
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt == "(":
            refs.append(_Ref("substitution", "", i, n, quote == '"'))
            return refs
        if nxt == "{":
            close = raw.find("}", i + 2)
            if close < 0:
                refs.append(_Ref("expansion", "", i, n, quote == '"'))
                return refs
            inner = raw[i + 2 : close]
            kind = "simple" if _NAME.fullmatch(inner) else "expansion"
            refs.append(_Ref(kind, inner if kind == "simple" else "", i, close + 1, quote == '"'))
            i = close + 1
            continue
        name = _NAME.match(raw, i + 1)
        if name:
            refs.append(_Ref("simple", name.group(0), i, name.end(), quote == '"'))
            i = name.end()
            continue
        if nxt in "0123456789@*#?$!-":
            refs.append(_Ref("special", nxt, i, i + 2, quote == '"'))
            i += 2
            continue
        i += 1
    return refs


def _quoted(raw: str, refs: list[_Ref]) -> str:
    """The word with every unquoted simple reference wrapped in double quotes."""
    return _splice(
        raw,
        [(r.start, r.end, f'"{raw[r.start : r.end]}"') for r in refs if r.kind == "simple" and not r.quoted],
    )


def _split_by_assignment(pieces: tuple[shell.Piece, ...]) -> set[str]:
    """Variables given a value earlier in the command that quoting would change: whitespace
    or a glob in it, or an expansion whose words cannot be known (a `mktemp` substitution
    is one path, so it is fine). One pass over the pieces."""
    names: set[str] = set()
    for piece in pieces:
        words = shell.words(piece.text)
        if words and words[0].raw in _DECLARERS:
            words = words[1:]
        for word in words:
            match = _ASSIGNMENT.fullmatch(word.raw)
            if not match:
                break  # assignments only stand at the start of a command
            inner = _unquoted(match.group(2))
            if _MKTEMP.fullmatch(inner):
                continue
            if any(ch in inner for ch in " \t\n*?[") or "$" in inner or "`" in inner:
                names.add(match.group(1))
    return names


# -- invariants -------------------------------------------------------------------------


def _is_narrowing(original: str, rewritten: str) -> bool:
    """Rule 2's mechanical half: the rewrite must not extend reach.

    Deliberately crude and deliberately strict — every check here is a reason to *refuse*
    to rewrite, and refusing is always safe.
    """
    if rewritten == original:
        return False
    # A rewrite must not introduce a new command separator: that would be a way to append
    # something the original never contained.
    for separator in (";", "&&", "||", "|", "\n"):
        if rewritten.count(separator) > original.count(separator) + (
            2 if separator == "&&" else 0
        ):
            return False
    # It must not introduce recursion or force that was not already there.
    for dangerous in ("sudo", "--no-preserve-root", "chmod", "chown", "mkfs", "dd "):
        if dangerous in rewritten and dangerous not in original:
            return False
    return True


def _still_safe(event: AgentEvent, candidate: dict) -> bool:
    """Rule 3: the rewritten arguments must have no high or critical finding left."""
    probe = event.model_copy(update={"arguments": candidate})
    return not any(f.severity in _SERIOUS for f in checks.risky_command(probe))


def finding_for(rewrite: Rewrite, event: AgentEvent) -> Finding:
    """Rule 4: the rewrite explains itself."""
    return Finding(
        category=ChallengeCategory.RISK,
        verdict=Verdict.SUPPORTED_WITH_RISK,
        # A narrowing rewrite is a thing Truthstone did, not a failure the agent made.
        # SPEC §3 has no entry for it and the census must not invent one.
        failure_mode=FailureMode.NOT_A_FAILURE,
        severity=Severity.MEDIUM,
        subject="modified command",
        summary=f"Truthstone narrowed this command: {rewrite.summary}",
        detail=rewrite.reason,
        evidence=[EvidenceRef(source="runtime", note=str(event.arg("command"))[:200])],
        suggestion="Run it as written if the original was intended.",
        level=EscalationLevel.DETERMINISTIC,
    )
