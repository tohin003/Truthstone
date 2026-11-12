"""C1, day 4: the names a request asserts beside today's premise rule, and how they are judged.

Ported from the frozen prototypes ``premise_proto_v43.py`` (v4.3) and ``premise_proto_v52.py``
(v5.2, written over v5.1 = ``premise_proto_v51.py``). The prototypes are the specification:
every regex, list and function below is theirs, and ``intent/premise.py`` calls them where the
prototypes' ``install()`` patched it. The prototypes' explicit ``P`` parameter is kept: ``P`` is
``truthstone.intent.premise``, which passes itself (no import cycle).

* **v4.3, "pointed back"** (``_pointed_back``): a sentence ties a switch to the project's own
  present behaviour, and that sentence or the next points back to it ("… when `X=1` is set:
  switch that on"). Its names are added beside today's assertions; a name both rules assert
  keeps today's assertion exactly.
* **v5.2, "used switch"** (``_used_switch``): the request uses a switch (sets, passes, enables,
  raises or lowers it, adds it to an invocation) that the project's own code owns and that
  resolves nowhere. A name v4.3 also asserts is noted when either rule's ownership test passes
  (``DualAnchor``).
* **C1b**: a symbol found only in history files, when every code file was read, is noted.
* **C1c**: the env switch-on rule is skipped when a tool is named in that name's clause
  (``premise._asserted``).
* **v5.2's final precision filter** (``_library_kwarg``) applies to every noted name, today's
  rule's included.
* **Day 5** (beyond the prototypes): in v4.3, a present-tense reading verb before the name in its
  own clause ("<program> reads `x` from <file>") is a capability marker beside a condition, "with"
  and "has a `x` option" (``_READS_BEFORE``), and "set/put … there" points back (``_verb_back``).
  Every other v4.3 guard is unchanged.

``USED_SWITCH_SPEAKS`` carries battery 3's registered decision. When it is False, the noted
names are v4.3's (today's rule, v4.3, C1b, C1c) after v5.2's final precision filter, exactly as
v4.3 alone notes them; what v5.2 would note beyond them goes to ``Premise.recorded`` only: never
noted, held, put on ``spec.premises`` or given to ``premise_unmet`` (``assertions()`` never
returns a name only the used-switch rule asserts).
"""

from __future__ import annotations

import functools
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Battery 3's registered decision (FIX-DESIGN v4, section C1): v5.2's honest-prompt notes (5/60)
# exceeded 1 and today's (4/60), so the used-switch rule is recorded only.
USED_SWITCH_SPEAKS = False

# Curly apostrophes read as "'" in every prompt reader (C6): premise.check and assertions are two.
_APOS = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})

# == v4.3 (premise_proto_v43.py) =====================================================================

# -- the back-reference (miss-2-3; struct-2-9: no content nouns) ------------------------------------
# <ref> = it/that/this/them/those, "the ≤2-word flag/option/setting/key" (and the other switch nouns
# v4.1 had: switch, variable, mode, helper), or the asserted name itself, repeated.
_REF_NOUN = r"(?:flag|option|setting|switch|variable|key|mode|helper)s?"
_PRONOUN_REF = r"(?:it|that|this|them|those)\b"
_NOUN_REF = rf"the\s+(?:[\w`'\".=/-]+\s+){{0,2}}?{_REF_NOUN}\b"


def _ref(name: str) -> str:
    named = rf"[`'\"]?{re.escape(name)}[`'\"]?(?![\w-])"
    return rf"(?:{_PRONOUN_REF}|{_NOUN_REF}|{named})"


def _verb_back(ref: str) -> str:
    return (
        rf"(?:(?:switch|turn|flip)\s+{ref}\s+on\b"
        rf"|(?:switch|turn|flip)\s+on\s+{ref}"
        rf"|(?:enable|activate|use|pass|apply|call|include)\s+{ref}"
        rf"|(?:put|add|wire)\s+{ref}\s+(?:in|into|to)\b"
        rf"|set\s+{ref}\s+(?:to\s+[`'\"]?[\w.-]+|on\b)"
        # day 5: values set at the place the sentence named ("set country DE and plan plus there")
        r"|(?:set|put)\s+[^.;:!?]{1,60}?\s+there\b)"
    )


_LABEL = r"(?:[A-Z][A-Za-z ]{0,20}:\s+)?"
_LEAD_WORDS = r"(?:(?:please|pls|so|and|then|now|just|also|can\s+you|could\s+you|would\s+you|will\s+you)\s+)*"
_LEAD_IN = r"\W*" + _LABEL + _LEAD_WORDS


@functools.lru_cache(maxsize=4096)
def _same_sentence_back(name: str) -> re.Pattern[str]:
    """A back-reference after the name in its own sentence."""
    return re.compile(r"\b" + _verb_back(_ref(name)), re.I)


@functools.lru_cache(maxsize=4096)
def _next_sentence_opener(name: str) -> re.Pattern[str]:
    """The next sentence opens (after lead-ins and a ``Label:``) with a back-reference, or with
    "turn on / switch on / enable / use / pass / set <ref>" (miss-2-3)."""
    ref = _ref(name)
    return re.compile(
        _LEAD_IN + rf"(?:{_verb_back(ref)}|(?:turn\s+on|switch\s+on|enable|use|pass|set)\s+{ref})", re.I
    )


# A sentence that opens with "turn on / switch on / enable" (design text; after lead-ins and a label).
_SWITCH_FIRST = re.compile(_LEAD_IN + r"(?:(?:switch|turn)\s+on|enable)\b", re.I)
# In such a sentence the capability clause follows a dash, ";", ":", "," or "since/because/as";
# the subject is taken from it (miss-2-3 "switch-first takes the subject from the capability sentence").
_CAP_SPLIT = re.compile(r"\s[-\u2013\u2014]{1,2}\s+|[;:,]\s+|\s+(?=(?:since|because|as)\s)", re.I)

# -- capability ------------------------------------------------------------------------------------
# Possession right before the name (+ article, optional "optional"), followed by a switch noun.
# miss-2-6 / rd1-2-6: takes/accepts/understands/honours/recognises/reads join the list.
_HAS_BEFORE = re.compile(
    r"\b(?:has|have|offers?|provides?|exposes?|supports?|comes\s+with|there's|there\s+is|we\s+have|we've\s+got"
    r"|takes?|accepts?|understands?|honou?rs?|recogni[sz]es?|reads?)\s+"
    r"(?:an?|the|its)\s+(?:optional\s+)?[`'\"]?$|'s\s+[`'\"]?$",
    re.I,
)
# "supports `<name>`" without an article, when the name is backticked or a flag (miss-2-6).
_SUPPORTS_NAME = re.compile(r"\bsupports?\s+[`'\"]?$", re.I)
_SWITCH_NOUN = re.compile(
    r"[`'\"]?\s*(?:option|flag|setting|switch|mode|toggle|helper|function|method|key)s?\b", re.I
)
_FLAG_WITH = re.compile(r"\b(?:with|via|passing|by\s+passing)\s+[`'\"]?$", re.I)
# Day 5: a present-tense reading verb in the name's own clause, before it and within 80 characters with
# no clause break: "<the project's program> reads `x` from <file>", "the CLI takes defaults for ... from
# `y`". It says the program reads the name today, as a condition or "has a `x` option" does.
_READS_BEFORE = re.compile(r"\b(?:reads|takes|loads|picks\s+up|pulls)\b[^.;:!?]{0,80}$", re.I)

# -- guards --------------------------------------------------------------------------------------
# Generic tool nouns (design text: "test runner", not a bare "runner").
_TOOL_NOUNS = re.compile(
    r"\b(?:test\s+runner|linter|formatter|type\s*checker|compiler|bundler|transpiler)s?\b", re.I
)
# Future, on the capability part only, exempting requests and politeness (miss-2-2, rd1-2-6).
_FUTURE = re.compile(
    r"\b(?:will(?!\s+you\b)|won't|going\s+to|(?:we|i|you|they)'ll"
    r"|would(?!\s+you\b|\s+be\s+(?:great|helpful)\b|\s+appreciate\b)|could(?!\s+you\b))\b",
    re.I,
)
# Creation or absence anywhere in the sentence or the next one (t2-2-8, widened).
_OBJ = (
    r"(?:it|that|this|them|the\s+(?:[\w`'\".=/-]+\s+){0,2}?(?:flag|option|setting|switch|key|variable)s?\b"
    r"|`[^`\n]+`)"
)
_SPAN_CREATES = re.compile(
    r"\b(?:is|are)\s+new\b"
    r"|\b(?:does|do)(?:n't|\s+not)\s+exist\b"
    r"|\bnot\s+(?:there|implemented)\s+yet\b"
    r"|\b(?:is|are)(?:n't|\s+not)\s+(?:yet\s+)?(?:implemented|supported|there|wired(?:\s+up)?)\b"
    r"|\b(?:is|are)\s+missing\b"
    rf"|\b(?:implement|create|build|introduce|wire\s+up)\s+{_OBJ}"
    rf"|\badd\s+{_OBJ}\s+(?:too|as\s+well|first)\b"
    rf"|\badd\s+{_OBJ}\s+to\s+(?:the\s+)?(?:(?:argument|arg|option|cli|command[-\s]line)\s+)?"
    r"(?:parser|cli|code|config\s+schema)\b",
    re.I,
)
# "add <obj> to <place>": creation when <place> is a parser or a source file (t2-2-8 (d)); passing
# it when <place> is an invocation (a CI step, a shell script, an npm script, a job).
_PLACE = r"(?P<place>(?:[^.;!?\n]|\.(?=\w))*)"  # a dot inside a path does not end the place
_ADD_TO_ANY = re.compile(rf"\badd\s+{_OBJ}\s+to\s+{_PLACE}", re.I)
_PARSER_PLACE = re.compile(
    r"(?:the\s+)?(?:(?:argument|arg|option|cli|command[-\s]line)\s+)?(?:parser|cli|code|config\s+schema)\b",
    re.I,
)
_PATH_PLACE = re.compile(r"(?:the\s+)?`?((?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]+)`?")
_SHELLISH = frozenset({".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".mk"})
_ADD_BEFORE = re.compile(r"\badd\s+[`'\"]?$", re.I)
_TO_AFTER = re.compile(r"[`'\"]?\s+to\s+" + _PLACE, re.I)

# -- the subject ---------------------------------------------------------------------------------
# Repeatable hedges (miss-2-7), a label, "per the X,"/"according to the X,"/"as documented".
_HEDGE_WORD = (
    r"(?:i'm\s+(?:pretty\s+|fairly\s+|quite\s+)?sure|(?:pretty|fairly|quite)\s+sure|i\s+think|i\s+believe"
    r"|i\s+remember|i\s+recall|as\s+far\s+as\s+i\s+know|afaik|iirc|fyi|so|hey|hi|hello|btw|apparently)"
    r"(?:\s+(?:team|all|folks|there))?(?:\s+that)?"
)
_HEDGES = rf"(?:{_HEDGE_WORD}\W+)*"
_PER = (
    r"(?:(?:per\s+the\s+[\w.-]+|according\s+to\s+the\s+[\w.-]+|as\s+documented(?:\s+in\s+[\w./-]+)?)\W+)?"
)
_PREFIX = re.compile(r"\W*" + _LABEL + _HEDGES + _PER, re.I)
# A leading subordinate clause, stripped before the own-subject test (miss-2-7, rd1-2-4 (a)).
_SUBORDINATE = re.compile(r"(?:when|if|once|whenever|with)\b[^,]{1,120},\s*", re.I)
_PRONOUN_SUBJ = re.compile(r"(?:it|this|that)\b", re.I)
_OWN_WORD = re.compile(r"(?:our|my|we)\b", re.I)
_THERE = re.compile(r"(?:there's|there\s+is|we\s+have|we've\s+got)\b", re.I)
_ARTICLE = re.compile(r"(the|its)\s+", re.I)
_SUBJECT_TOKEN = re.compile(r"[`'\"]?((?:[\w.-]+/)*[\w.-]*[A-Za-z_][\w.-]*(?:\(\))?)[`'\"]?")
_CODE_LIKE = re.compile(r"[_./\d-]|[a-z][A-Z]|\(\)$")
_OWN_CODE_TOKEN = re.compile(
    r"`([^`\n]+)`|([A-Za-z_]\w*(?:\.\w+)*\(\)|[a-z]+(?:_[a-z0-9]+)+|[a-z]+(?:[A-Z][a-z0-9]+)+)"
)

# -- candidates only this rule reads (rd1-2-8: never reach today's rule) -----------------------------
_KEY_VALUE = re.compile(
    r"`\s*\{?\s*([A-Za-z_][\w-]{2,})\s*[:=]\s*(?:true|false|on|off|yes|no|\d+|'[^']*'|\"[^\"]*\")\s*\}?\s*`",
    re.I,
)
_ENV_ONE = re.compile(r"`([A-Z][A-Z0-9]{3,})=[^`\s]+`")
_CODE_SPANS = re.compile(r"`[^`\n]*`|(?:[\w.-]+/)+[\w.-]+")

# -- a fixed list of tool / runtime / framework switches: external (t2-2-5, rd1-2-8) ---------------
_FIXED_FLAGS = frozenset(
    {
        # pytest and its plugins
        "--durations", "--durations-min", "--maxfail", "--lf", "--last-failed", "--ff", "--failed-first",
        "--pdb", "--tb", "--showlocals", "--junitxml", "--junit-xml", "--log-cli-level", "--disable-warnings",
        "--strict-markers", "--cov", "--cov-report", "--cov-fail-under", "--reruns", "--numprocesses",
        "--randomly-seed", "--doctest-modules", "--runxfail", "--setup-show", "--collect-only",
        # node
        "--inspect", "--inspect-brk", "--heapsnapshot-signal", "--heapsnapshot-near-heap-limit",
        "--max-old-space-size", "--enable-source-maps", "--trace-warnings", "--trace-deprecation",
        "--trace-uncaught", "--unhandled-rejections", "--cpu-prof", "--heap-prof", "--prof",
        "--stack-trace-limit", "--experimental-vm-modules", "--env-file", "--abort-on-uncaught-exception",
        # Typer / Click
        "--show-completion", "--install-completion",
        # jest / vitest / playwright / mocha
        "--reporter", "--runInBand", "--detectOpenHandles", "--maxWorkers", "--testTimeout",
        "--updateSnapshot", "--update-snapshots", "--passWithNoTests", "--pass-with-no-tests",
        "--forbid-only", "--headed",
        "--max-failures", "--watchAll", "--onlyChanged", "--clearCache", "--logHeapUsage",
        # package managers, tsc, git
        "--frozen-lock" "file",  # one literal, split for the leakage lint's token scan
        "--legacy-peer-deps", "--prefer-offline", "--no-audit", "--no-cache-dir",
        "--ignore-scripts", "--noEmit", "--extendedDiagnostics", "--traceResolution", "--no-verify",
        "--force-with-lease",
    }
)
_FIXED_ENV = frozenset(
    {
        "PWDEBUG", "DEBUG_PRINT_LIMIT", "WEB_CONCURRENCY", "PORT", "HOST", "HOSTNAME", "WORKERS",
        "BUILDKIT_PROGRESS", "DJANGO_SETTINGS_MODULE", "RAILS_ENV", "RAILS_MAX_THREADS", "RACK_ENV",
        "RAILS_LOG_TO_STDOUT", "NEXT_TELEMETRY_DISABLED", "SENTRY_DSN", "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
    }
)
_FIXED_ENV_PREFIX = re.compile(
    r"^(?:(?:PLAYWRIGHT|PUPPETEER|CYPRESS|POETRY|PDM|HATCH|COMPOSE|GUNICORN|UVICORN|FLASK)_\w+|TF_(?!VAR_)\w+)$"
)


def _fixed_external(name: str) -> bool:
    bare = name.removesuffix("()")
    return bare in _FIXED_FLAGS or bare in _FIXED_ENV or _FIXED_ENV_PREFIX.match(bare) is not None


# -- resolution ------------------------------------------------------------------------------------
# rd1-2-9: these widen premise resolution only (resolve and the subject checks), not premise_unmet.
_EXTRA_SUFFIXES = frozenset(
    {".mts", ".cts", ".pyx", ".kts", ".cxx", ".hxx", ".sql", ".proto", ".graphql", ".tf"}
)
_FILE_SUFFIXES = frozenset(
    {".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".md", ".rst", ".txt", ".env",
     ".xml", ".html", ".css", ".scss", ".lock", ".properties", ".csv"}
)
_HISTORY = re.compile(  # = spec_integrity._LOG
    r"^(?:changelog|changes|history|news|release[-_ ]?notes|releases)(?:\.|$)", re.I
)
# miss-2-21: where a half-wired switch lives.
_CI_FILE = re.compile(
    r"^(?:\.github/(?:workflows|actions)/.+|\.gitlab-ci\.ya?ml|\.circleci/.+|(?:.*/)?Jenkinsfile|azure-pipelines\.ya?ml"
    r"|\.travis\.ya?ml|bitbucket-pipelines\.ya?ml|\.buildkite/.+|\.drone\.ya?ml|appveyor\.ya?ml|cloudbuild\.ya?ml)$"
)
_COMPOSE_FILE = re.compile(r"^(?:.*/)?(?:docker-)?compose(?:\.[\w-]+)*\.ya?ml$", re.I)
_ENV_TEMPLATE = re.compile(
    r"^(?:.*/)?(?:\.?env\.(?:example|sample|template|dist|defaults)|(?:example|sample|template)\.env)$", re.I
)
# An own subject that is the CI setup or the compose stack: its files are the subject's own.
_CI_NOUN = re.compile(r"\b(?:workflows?|pipelines?|ci|jobs?|actions?)\b", re.I)
_COMPOSE_NOUN = re.compile(r"\b(?:compose|stack|containers?|docker)\b", re.I)

# -- forwarding (t2-2-5 (e), t2-2-7) ----------------------------------------------------------------
_SHELL_FORWARD = re.compile(r"\"\$@\"|\$@|\"\$\*\"|\$\*")
_NODE_FORWARD = re.compile(
    r"\.\.\.\s*process\.argv|\b(?:spawn|spawnSync|exec|execSync|execFile|execFileSync|fork|execa|execaSync)"
    r"\s*\([^;]*?process\.argv",
    re.S,
)

# -- the pronoun's previous object (t2-2-6) ---------------------------------------------------------
_USE_VERB = re.compile(
    r"\b(?:use[sd]?|using|added|adopt(?:s|ed)?|install(?:s|ed)?|depend(?:s|ed)?\s+on|rel(?:y|ies|ied)\s+on"
    r"|test(?:s|ed)?\s+with|runs?\s+(?:on|with)|ran\s+(?:on|with)|buil[dt]s?\s+(?:on|with)|switched\s+to"
    r"|moved\s+to|migrated\s+to|upgraded|bumped|pinned)\s+(?:(?:the|a|an|our|its)\s+)?(`[^`\n]+`|[@\w][\w.@/-]*)",
    re.I,
)
_LIB_NOUN = re.compile(
    r"^\s*`?\s*(?:library|package|module|sdk|framework|plugin|dependency|gem|crate|client|cli|tool)\b", re.I
)


# -- the subject of a sentence -------------------------------------------------------------------
@dataclass(frozen=True)
class Subject:
    kind: str = ""  # "own" | "generic" | "pronoun" | "token" | ""
    token: str = ""  # token subjects: the token; own subjects: a code token right after our/my
    backticked: bool = False
    absolute: bool = False
    phrase: str = ""  # own subjects: the three words after our/my ("nightly workflow publishes")
    end: int = 0  # where the predicate starts in the analysed text


@dataclass(frozen=True)
class Anchor:
    subject: Subject  # the effective subject (a pronoun's is the one it inherits)
    pronoun: bool = False
    preds: tuple[str, ...] = ()  # the predicates a pronoun reaches back over


def _words(text: str, start: int, n: int) -> str:
    return " ".join(re.findall(r"`[^`\n]+`|[\w.()/-]+", text[start:])[:n]).lower()


def _subject(text: str) -> Subject:
    pos = _PREFIX.match(text).end()
    sub = _SUBORDINATE.match(text, pos)
    if sub:
        pos = _PREFIX.match(text, sub.end()).end()
    m = _PRONOUN_SUBJ.match(text, pos)
    if m:
        return Subject("pronoun", end=m.end())
    m = _THERE.match(text, pos)
    if m:
        return Subject("own", end=m.end(), phrase=_words(text, m.end(), 3))
    m = _OWN_WORD.match(text, pos)
    if m:
        token = ""
        head = re.match(r"\s+(\S+)(?:\s+(\S+))?", text[m.end():])
        if head:
            for word in head.groups():
                if not word:
                    continue
                code = _OWN_CODE_TOKEN.fullmatch(word.strip(",;:.'\""))
                if code:
                    token = (code.group(1) or code.group(2)).strip()
                    break
        return Subject("own", token=token, end=m.end(), phrase=_words(text, m.end(), 3))
    art = _ARTICLE.match(text, pos)
    at = art.end() if art else pos
    if art and art.group(1).lower() == "the" and text[at : at + 1] != "`":
        word = re.match(r"[\w.-]+", text[at:])
        # v4.3: own only via _generic_files
        return Subject("generic", end=at + (word.end() if word else 0), phrase=_words(text, at, 3))
    t = _SUBJECT_TOKEN.match(text, at)
    if not t:
        return Subject("", end=at)
    token = t.group(1).rstrip(".")
    lead = text[:at]
    backticked = text[at : at + 1] == "`" or lead.endswith("`") or lead.endswith("`/")
    absolute = lead.endswith("/")
    return Subject(
        "token",
        token=("/" + token) if absolute else token,
        backticked=backticked,
        absolute=absolute,
        end=t.end(),
    )


def _capability_clause(sentence: str, start: int) -> str:
    m = _CAP_SPLIT.search(sentence, start)
    if not m:
        return ""
    return re.sub(r"^(?:since|because|as)\s+", "", sentence[m.end():], flags=re.I)


# -- candidates ----------------------------------------------------------------------------------
def _c1_candidates(P, sentence: str):
    found = list(P._candidates(sentence))
    have = {c.name for _, c in found}
    kv: set[str] = set()
    for m in _KEY_VALUE.finditer(sentence):
        key = m.group(1)
        kv.add(key)
        if key not in have and not _fixed_external(key):
            found.append((m.start(1), P.Assertion(key, "name", (key,))))
            have.add(key)
    for m in _ENV_ONE.finditer(sentence):
        name = m.group(1)
        if name not in have and not P._WELL_KNOWN_ENV.match(name) and not _fixed_external(name):
            found.append((m.start(1), P.Assertion(name, "env", (name,))))
            have.add(name)
    return sorted(found, key=lambda item: item[0]), kv


def _four_kind(cand, sentence: str, offset: int, kv: set[str]) -> bool:
    """`--flags`, `NAME=value`, dotted and `key: value` names (t2-2-5): the whole-sentence tool guard."""
    if cand.kind == "flag" or cand.name in kv:
        return True
    end = offset + len(cand.name)
    if cand.kind == "env" and sentence[end : end + 1] == "=":
        return True
    return "." in cand.name.removesuffix("()")


def _backticked_at(sentence: str, offset: int) -> bool:
    return offset > 0 and sentence[offset - 1] in "`'\""


def _source_file(P, path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(name).suffix
    return (
        suffix in (P._CODE_SUFFIXES | _EXTRA_SUFFIXES)
        and suffix not in _SHELLISH
        and name not in P._CODE_NAMES
    )


def _place_kind(P, place: str) -> str:
    if _PARSER_PLACE.match(place):
        return "parser"
    m = _PATH_PLACE.match(place)
    if m and _source_file(P, m.group(1)):
        return "source"
    return "invocation"


def _creates(P, span: str) -> bool:
    if _SPAN_CREATES.search(span):
        return True
    return any(_place_kind(P, m.group("place")) == "source" for m in _ADD_TO_ANY.finditer(span))


# -- the rule ------------------------------------------------------------------------------------
def _pointed_back(P, prompt: str):
    """[(Assertion, Anchor)] for every name this rule asserts, in prompt order (structural checks
    only; the repository checks run in ``check``)."""
    sents = [s for _, s in P._sentences(prompt or "")]
    out = []
    chain_subject: Subject | None = None
    chain_preds: list[str] = []
    for i, s in enumerate(sents):
        nxt = sents[i + 1] if i + 1 < len(sents) else ""
        first = _SWITCH_FIRST.match(s)
        analysed = s
        if first:
            analysed = _capability_clause(s, first.end())
            raw = _subject(analysed) if analysed else Subject("")
        else:
            raw = _subject(s)
        pred = analysed[raw.end :] if analysed else ""
        if raw.kind == "pronoun":
            eff, preds, pronoun = chain_subject, tuple(chain_preds), True
            chain_preds = [*chain_preds, pred]
        else:
            eff, preds, pronoun = raw, (), False
            chain_subject, chain_preds = raw, [pred]
        if eff is None or eff.kind in ("", "pronoun"):
            continue  # v4.3: a generic "the X" subject is judged against the repository in _keeps_note
        if P._CREATING_SENTENCE.search(s):
            continue
        span = s + " " + nxt
        if _creates(P, span):
            continue  # creation or absence anywhere in the sentence or the next (t2-2-8)
        candidates, kv = _c1_candidates(P, s)
        for offset, cand in candidates:
            name = cand.name
            if cand.kind == "path":
                continue
            if eff.token and name.removesuffix("()") == eff.token.removesuffix("()").lstrip("/"):
                continue  # the subject itself
            back = _same_sentence_back(name).search(s, offset + len(name))
            if back:
                limit, back_text = back.start(), ""
            elif nxt and _next_sentence_opener(name).match(nxt):
                limit, back_text = len(s), nxt
            elif first:
                limit, back_text = len(s), ""
            else:
                continue
            capability = _CODE_SPANS.sub(" ", s[:limit])
            if _FUTURE.search(capability):
                continue  # future, on the capability part only (miss-2-2)
            if _four_kind(cand, s, offset, kv):
                # tool guard over the whole sentence (and the switch-on sentence), own or not (t2-2-5)
                text = (s + " " + back_text).replace(name, " ")
                if P._TOOL_NAMED.search(text) or _TOOL_NOUNS.search(text):
                    continue
            elif P._TOOL_NAMED.search(capability) or (eff.kind != "own" and _TOOL_NOUNS.search(capability)):
                continue
            before = s[:offset]
            has = _HAS_BEFORE.search(before[-48:])
            supports = (cand.kind == "flag" or _backticked_at(s, offset)) and _SUPPORTS_NAME.search(
                before[-24:]
            )
            window = P._window(before)
            if P._ABSENT.search(window):
                continue
            if not (has or supports) and P._CREATES.search(window):
                continue
            clause = _CODE_SPANS.sub(" ", P._clause(s, offset, len(name)))
            if P._BUILDS.search(clause):
                continue
            after = s[offset + len(name) :]
            lead = s[P._clause_start(s, offset) : offset][-160:]
            cond = P._CONDITION.search(lead)
            reads = _READS_BEFORE.search(lead)  # day 5
            flag_with = cand.kind == "flag" and _FLAG_WITH.search(before[-24:])
            if not (cond or reads or flag_with or supports or (has and _SWITCH_NOUN.match(after))):
                continue
            out.append((P.Assertion(name, cand.kind, cand.keys, existing=True), Anchor(eff, pronoun, preds)))
    return out


def _created(P, prompt: str, pb_names: set[str]) -> set[str]:
    """Names the prompt creates (creation word in the 4-word window, possession or "supports
    `<name>`" exempt), except "add `<name>` to <invocation>" for a name this rule asserted."""
    created: set[str] = set()
    for _start, sentence in P._sentences(prompt or ""):
        candidates, _kv = _c1_candidates(P, sentence)
        for offset, c in candidates:
            before = sentence[:offset]
            if not P._CREATES.search(P._window(before)):
                continue
            if _HAS_BEFORE.search(before[-48:]):
                continue
            if (c.kind == "flag" or _backticked_at(sentence, offset)) and _SUPPORTS_NAME.search(before[-24:]):
                continue
            if c.name in pb_names and _ADD_BEFORE.search(before[-12:]):
                m = _TO_AFTER.match(sentence[offset + len(c.name) :])
                if m and _place_kind(P, m.group("place")) == "invocation":
                    continue  # "add `--totals` to `scripts/nightly.sh`": passing it, not making it
            created.add(c.name)
    return created


def _c1(P, prompt: str, base_names: set[str]):
    pb = _pointed_back(P, prompt)
    created = _created(P, prompt, {a.name for a, _ in pb})
    out, seen = [], set()
    for a, anchor in pb:
        if a.name in base_names or a.name in created or a.name in seen:
            continue  # today's assertion stays as it is (rd1-2-1)
        seen.add(a.name)
        out.append((a, anchor))
    return out


def _variants(name: str) -> tuple[str, ...]:
    bare = name.lstrip("-").removesuffix("()")
    out = {bare}
    if bare.startswith(("no-", "no_")):
        out.add(bare[3:])
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", bare.replace("-", "_"))
    if words:
        low = [w.lower() for w in words]
        out |= {
            "_".join(low), "-".join(low), "_".join(low).upper(), low[0] + "".join(w.title() for w in low[1:])
        }
    if name.startswith("--"):
        out |= {"--" + v for v in list(out) if "_" not in v and not v.isupper()}
    return tuple(sorted(out))


# -- repository checks (one context per check) ---------------------------------------------------
class _Ctx:
    def __init__(self, P, root, files, prompt):
        from truthstone.repo import scanner

        self.P, self.root, self.prompt = P, Path(root), prompt
        self.is_test = scanner.is_test_path
        self.files = list(files)
        present = set(self.files)
        self.all_files = self.files + [r for r in P.dot_config_files(self.root) if r not in present]
        self._text: dict[str, str] = {}
        self._defs: dict[str, list[str]] = {}
        self._packages: set[str] | None = None
        self._names: set[str] | None = None
        self._code: list[str] | None = None

    def wide_code(self, rel: str) -> bool:
        name = rel.rpartition("/")[2].lower()
        return (
            PurePosixPath(name).suffix in (self.P._CODE_SUFFIXES | _EXTRA_SUFFIXES)
            or name in self.P._CODE_NAMES
            or name.startswith(("dockerfile.", "makefile."))
        )

    def code_files(self) -> list[str]:
        if self._code is None:
            self._code = [r for r in self.all_files if self.wide_code(r) and not self.is_test(r)]
        return self._code

    def text(self, rel: str) -> str:
        if rel not in self._text:
            try:
                full = self.root / rel
                self._text[rel] = (
                    full.read_text(encoding="utf-8", errors="ignore")
                    if full.stat().st_size <= self.P.MAX_FILE_BYTES
                    else ""
                )
            except OSError:
                self._text[rel] = ""
        return self._text[rel]

    def scan_complete(self) -> bool:
        """C1b only when the scan reads every code file: no size skip, nothing unreadable (t2-2-13)."""
        for rel in self.all_files:
            if not self.wide_code(rel):
                continue
            try:
                if (self.root / rel).stat().st_size > self.P.MAX_FILE_BYTES:
                    return False
            except OSError:
                return False
        return True

    def defs(self, name: str) -> list[str]:
        """Non-test code files that define ``name`` (``def/class/function/const/let/var/interface/
        type/enum <name>`` or ``<name> =``/``:`` at line start), within MAX_SCAN_BYTES."""
        if name not in self._defs:
            define = re.compile(
                rf"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function|const|let|var|interface|type|enum)"
                rf"\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*[:=](?!=)",
                re.M,
            )
            found, budget = [], self.P.MAX_SCAN_BYTES
            for rel in self.code_files():
                text = self.text(rel)
                budget -= len(text)
                if budget < 0:
                    break
                if name in text and define.search(text):
                    found.append(rel)
            self._defs[name] = found
        return self._defs[name]

    def project_names(self) -> set[str]:
        if self._names is None:
            names = {self.root.name}
            try:
                if (self.root / "pyproject.toml").is_file():
                    names.add(
                        str(
                            (
                                tomllib.loads((self.root / "pyproject.toml").read_text()).get("project") or {}
                            ).get("name", "")
                        )
                    )
                if (self.root / "package.json").is_file():
                    names.add(str(json.loads((self.root / "package.json").read_text()).get("name", "")))
            except Exception:  # noqa: BLE001 - an unreadable manifest names nothing
                pass
            self._names = {n.lower() for n in names if n}
        return self._names

    def packages(self) -> set[str]:
        if self._packages is None:
            self._packages = self.P._packages(self.root, self.prompt)
        return self._packages

    def imports_of(self, rels) -> set[str]:
        """Local files the given files import directly (Python modules, relative JS/TS imports)."""
        out: set[str] = set()
        present = set(self.all_files)
        for rel in rels:
            text = self.text(rel)
            base = PurePosixPath(rel).parent
            if rel.endswith((".py", ".pyi", ".pyx")):
                for m in re.finditer(r"^\s*(?:from\s+(\.*[\w.]*)\s+import|import\s+([\w.]+))", text, re.M):
                    mod = m.group(1) or m.group(2) or ""
                    dots = len(mod) - len(mod.lstrip("."))
                    parts = [p for p in mod.lstrip(".").split(".") if p]
                    if dots:
                        roots = ["/".join(base.parts[: max(0, len(base.parts) - (dots - 1))])]
                    else:
                        roots = ["", "src"]  # an absolute module, at the root or in a src/ layout
                    for r in roots:
                        stem = "/".join(x for x in [r, *parts] if x)
                        if not stem:
                            continue
                        for cand in (f"{stem}.py", f"{stem}/__init__.py"):
                            if cand in present:
                                out.add(cand)
            else:
                for m in re.finditer(
                    r"(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['\"](\.{1,2}/[^'\"]+)['\"]",
                    text,
                    re.M,
                ):
                    norm: list[str] = []
                    for part in base.joinpath(m.group(1)).parts:
                        if part == "..":
                            if norm:
                                norm.pop()
                        elif part != ".":
                            norm.append(part)
                    stem = "/".join(norm)
                    for cand in [
                        stem,
                        *[
                            stem + ext
                            for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
                        ],
                        *[f"{stem}/index{ext}" for ext in (".ts", ".tsx", ".js")],
                    ]:
                        if cand in present:
                            out.add(cand)
        return out - set(rels)


def _is_pathlike(bare: str, P) -> bool:
    suffix = PurePosixPath(bare).suffix.lower()
    return "/" in bare or suffix in (P._CODE_SUFFIXES | _EXTRA_SUFFIXES | _FILE_SUFFIXES)


_GENERIC_HEAD_STOP = frozenset(
    """script scripts tool tools command commands module modules file files job jobs service
services app application program library package code project repo repository function functions class
method helper helpers endpoint api page component task step pipeline workflow config configuration
settings server process
""".split()  # noqa: SIM905 - the prototype's word list
)
_GENERIC_NEVER = frozenset(
    "test tests suite suites runner runners spec specs linter formatter compiler bundler".split()  # noqa: SIM905
)


def _norm_stem(word: str) -> str:
    return re.sub(r"[-_.]", "", word.lower())


def _generic_files(subject: Subject, ctx: _Ctx) -> set[str]:
    """v4.3: "the X" is the project's own when a head word of X names a non-test code file (its
    stem), the project, or the project's CLI; test and tool nouns never are."""
    if subject.kind != "generic" or not subject.phrase:
        return set()
    words = [w.strip(",;:.'\"()").lower() for w in subject.phrase.split()[:2]]
    words = [w for w in words if w and not w.startswith("`")]
    if any(w in _GENERIC_NEVER for w in words):
        return set()
    if words and _TOOL_NOUNS.search(" ".join(words)):
        return set()
    out: set[str] = set()
    for w in words:
        if w in _GENERIC_HEAD_STOP and w != "cli":
            continue
        if w in ctx.project_names():
            return set(ctx.code_files())
        key = _norm_stem(w)
        if not key or ctx.P._TOOL_NAMED.fullmatch(w):
            continue
        for f in ctx.code_files():
            stem = _norm_stem(PurePosixPath(f).name.split(".")[0])
            if stem == key or (w == "cli" and (stem in ("cli", "main", "__main__") or f.startswith("bin/"))):
                out.add(f)
        if out:
            break
    return out


def _project_owned(subject: Subject, ctx: _Ctx) -> bool:
    """The design text's own-subject list, checked against the repository."""
    P = ctx.P
    if subject.kind == "own":
        return True
    if subject.kind != "token" or not subject.token:
        return False
    bare = subject.token.removesuffix("()")
    if subject.absolute or bare.startswith("/") or ".." in bare.split("/"):
        return False  # rd1-2-4 (c)
    if P._TOOL_NAMED.fullmatch(bare):
        return False
    if _is_pathlike(bare, P):  # rd1-2-4 (d): a dotted identifier is not a path
        if P._tool_owned(bare):
            return False
        files = ctx.all_files
        return (
            bare in files
            or any(f.startswith(bare.rstrip("/") + "/") for f in files)
            or (ctx.root / bare).exists()
        )
    if bare.lower() in ctx.project_names():
        return True
    if not (subject.backticked or _CODE_LIKE.search(bare) or bare[:1].isupper()):
        return False
    last = bare.rpartition(".")[2]
    if not last:
        return False
    if any(PurePosixPath(f).name.split(".")[0] == last for f in ctx.code_files()):  # rd1-2-4 (e): non-test
        return True
    return bool(ctx.defs(last))


def _def_files(token: str, ctx: _Ctx) -> set[str]:
    last = token.removesuffix("()").rpartition(".")[2]
    if not last:
        return set()
    named = {f for f in ctx.code_files() if PurePosixPath(f).name.split(".")[0] == last}
    return named | set(ctx.defs(last))


def _subject_files(anchor: Anchor, ctx: _Ctx) -> set[str]:
    """The subject's file and its imports (miss-2-21: where a case variant may resolve)."""
    subject = anchor.subject
    if subject.kind == "generic":
        files = _generic_files(subject, ctx)
        return files | ctx.imports_of(files)
    if subject.kind == "own":
        if subject.token:
            defs = _def_files(subject.token, ctx)
            if defs:
                return defs | ctx.imports_of(defs)
        selected: set[str] = set()
        if _CI_NOUN.search(subject.phrase):
            selected |= {f for f in ctx.all_files if _CI_FILE.match(f)}
        if _COMPOSE_NOUN.search(subject.phrase):
            selected |= {f for f in ctx.all_files if _COMPOSE_FILE.match(f)}
        return selected or set(ctx.code_files())
    bare = subject.token.removesuffix("()")
    if _is_pathlike(bare, ctx.P):
        return {bare} | ctx.imports_of({bare})
    if bare.lower() in ctx.project_names():
        return set(ctx.code_files())
    defs = _def_files(bare, ctx)
    return defs | ctx.imports_of(defs)


def _balanced(text: str, open_at: int) -> tuple[str, int]:
    depth = 0
    for i in range(open_at, min(len(text), open_at + 4000)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : i], i + 1
    return text[open_at + 1 : open_at + 4000], open_at + 4000


def _definition_forwards(text: str, name: str, rel: str) -> bool:
    n = re.escape(name)
    if rel.endswith((".py", ".pyi", ".pyx")):
        for m in re.finditer(rf"^\s*(?:async\s+)?def\s+{n}\s*\(", text, re.M):
            params, _end = _balanced(text, m.end() - 1)
            if re.search(r"\*\*\s*[A-Za-z_]\w*", params):
                return True  # **kwargs
        return False
    heads = (
        rf"\bfunction\s*\*?\s*{n}\s*(?:<[^>]*>)?\s*\(",
        rf"\b(?:const|let|var)\s+{n}\s*(?::[^=\n]+)?=\s*(?:async\s*)?(?:function\s*)?\(",
        rf"^\s*(?:async\s+)?{n}\s*\(",
    )
    for head in heads:
        for m in re.finditer(head, text, re.M):
            params, end = _balanced(text, m.end() - 1)
            if re.search(r"\.\.\.\s*[A-Za-z_$]", params):
                return True  # ...options rest parameter
            names = [p for p in re.findall(r"(?:^|,)\s*\{?\s*([A-Za-z_$][\w$]*)", params) if p]
            body = text[end : end + 3000]
            if any(re.search(rf"\.\.\.\s*{re.escape(p)}\b", body) for p in names):
                return True  # { ...options } spread of its own parameter
            if _NODE_FORWARD.search(body):
                return True
    return False


def _forwards(subject: Subject, ctx: _Ctx, definition_forwards) -> bool:
    """A subject whose definition forwards arguments is skipped (t2-2-5 (e), t2-2-7).
    ``definition_forwards`` is the definition test: v4.3's ``_definition_forwards``, or the
    ``_definition_forwards_v51`` that v5.2's install puts in its place."""
    if subject.kind == "token":
        bare = subject.token.removesuffix("()")
        if _is_pathlike(bare, ctx.P):
            text = ctx.text(bare)
            if not text:
                return False
            first_line = text.split("\n", 1)[0]
            shellish = PurePosixPath(bare).suffix.lower() in {".sh", ".bash", ".zsh"} or (
                first_line.startswith("#!") and re.search(r"\b(?:ba|z|da)?sh\b", first_line) is not None
            )
            return bool((shellish and _SHELL_FORWARD.search(text)) or _NODE_FORWARD.search(text))
        name = bare.rpartition(".")[2]
    elif subject.kind == "own" and subject.token:
        name = subject.token.removesuffix("()").rpartition(".")[2]
    elif subject.kind == "generic":
        for rel in _generic_files(subject, ctx):
            text = ctx.text(rel) or ""
            first_line = text.split("\n", 1)[0]
            shellish = PurePosixPath(rel).suffix.lower() in {".sh", ".bash", ".zsh"} or (
                first_line.startswith("#!") and re.search(r"\b(?:ba|z|da)?sh\b", first_line) is not None
            )
            if (shellish and _SHELL_FORWARD.search(text)) or _NODE_FORWARD.search(text):
                return True
        return False
    else:
        return False
    return any(definition_forwards(ctx.text(rel), name, rel) for rel in ctx.defs(name))


def _external_object(preds: tuple[str, ...], ctx: _Ctx) -> bool:
    """The sentences a pronoun reaches back over name a package, a library or a tool (t2-2-6)."""
    packages = ctx.packages()
    for pred in preds:
        if ctx.P._TOOL_NAMED.search(pred):
            return True
        for bt, word in re.findall(r"`([^`\n]+)`|([@A-Za-z][\w.@/-]*)", pred):
            if (bt or word).strip().lower() in packages:
                return True
        for m in _USE_VERB.finditer(pred):
            obj = m.group(1)
            backticked = obj.startswith("`")
            obj = obj.strip("`").strip()
            if _LIB_NOUN.match(pred[m.end() :]):
                return True
            if obj and not _project_owned(Subject("token", token=obj, backticked=backticked), ctx):
                return True
    return False


def _keeps_note(anchor: Anchor, ctx: _Ctx, definition_forwards) -> bool:
    subject = anchor.subject
    if subject is None or subject.kind in ("", "pronoun"):
        return False
    if anchor.pronoun and _external_object(anchor.preds, ctx):
        return False
    if subject.kind == "generic":
        return bool(_generic_files(subject, ctx)) and not _forwards(subject, ctx, definition_forwards)
    if not _project_owned(subject, ctx):
        return False
    return not _forwards(subject, ctx, definition_forwards)


def _variant_resolves(assertion, anchor: Anchor, ctx: _Ctx) -> bool:
    """Case variants resolve only inside the subject's file or its imports (miss-2-21)."""
    keys = set(assertion.keys)
    variants = [v for v in _variants(assertion.name) if v and v not in keys]
    if not variants:
        return False
    for rel in _subject_files(anchor, ctx):
        text = ctx.text(rel)
        for v in variants:
            if v in text and re.search(rf"(?<![\w-]){re.escape(v)}(?![\w-])", text):
                return True
    return False


def _note_file(rel: str, subject_files: set[str]) -> bool:
    """For a C1-asserted name: occurrences here still give the "appears only in" note — docs, and
    CI, compose and env-template files (miss-2-21) — unless the file is the subject's own."""
    from truthstone.validate import spec_integrity

    if rel in subject_files:
        return False
    return spec_integrity.is_doc_path(rel) or bool(
        _CI_FILE.match(rel) or _COMPOSE_FILE.match(rel) or _ENV_TEMPLATE.match(rel)
    )


# -- the note's words (struct-2-10, comp-2-37: C1b says the accurate fact) ------------------------
_DEFINES = "`{name}` appears only in {files}, and no code in this repository defines it"


def listed_files(files: list[str]) -> str:
    """Up to three files, and how many more."""
    return ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")


# == v5.2 (premise_proto_v52.py) =====================================================================

_SW_NOUN = (
    r"(?:option|flag|setting|switch|mode|toggle|key|variable|var|env\s+var|environment\s+variable|argument|arg"
    r"|parameter|param|kwarg|keyword\s+argument|property|field|attribute)s?"
)
_NOUNED = re.compile(r"`([A-Za-z_][\w-]{2,})`\s+(?:(?:[a-z]+[\s-]+){0,2})?" + _SW_NOUN + r"\b", re.I)
_ENV_NOUN = re.compile(r"\b(?:environment\s+variable|env\s+var|variable)s?\b", re.I)
_KEY_NOUN = re.compile(r"\bkeys?\b", re.I)
_ENV_ASSIGN = re.compile(r"(?<![\w$])`?([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{4,})=([^\s`]+)`?")
_KW_ASSIGN = re.compile(r"`[^`\n]*?(?<![\w.\-\"'])([a-z_][A-Za-z0-9_]{2,})(?![\"'])\s*(=|:)\s*(?!=)[^`\n]*`")
_CALL_KW = re.compile(r"`@?([A-Za-z_][\w.]*)\(([^`\n]*)\)`")
_CONFIG_NAMED = re.compile(r"[\w./-]+\.(?:json|jsonc|ya?ml|toml|ini|cfg|conf)\b", re.I)
_QUOTED_KEY = re.compile(r"`\s*\{?\s*\"([A-Za-z_][\w-]{2,})\"\s*:[^`]*`")
_SET_TO = re.compile(
    r"\b(?:set|sets|setting|raise|raises|lower|lowers|increase|increases|decrease|decreases|bump|bumps|reduce"
    r"|reduces|change|changes)\s+`([A-Za-z_][\w-]{2,})`(?:\s*\([^)]{0,120}\))?\s+(?:to|=)\s+\S",
    re.I,
)
_USE = re.compile(
    r"\b(?:use|uses|using|enable|enables|enabling|turn(?:s|ing)?\s+(?:it\s+|that\s+|this\s+|them\s+)?on|switch(?:es|ing)?"
    r"\s+(?:it\s+|that\s+)?on|flip\s+(?:it\s+)?on|set|sets|setting|pass|passes|passing|add|adds|prefix|prefixes|put"
    r"|call|calls|construct|constructs|build\s+.{0,40}?\bwith|run|runs|invoke|apply|export|include|configure"
    r"|raise|lower|increase|decrease|bump|reduce)\b",
    re.I,
)
# own words: possession or the project itself, not a bare "we" ("we'd like", "we keep")
_OWN = re.compile(
    r"\b(?:our|my)\s+[A-Za-z`]|\b(?:we've\s+got|we\s+have|there's|the\s+project's|the\s+app(?:'s)?\b"
    r"|the\s+application\b)",
    re.I,
)
_THE_X = re.compile(r"\bthe\s+([a-z][\w-]*)(?:'s)?(?:\s+([a-z][\w-]*))?", re.I)
_BACKTICK = re.compile(r"`([^`\n]+)`")
_BARE_PATH = re.compile(
    r"(?<![\w`/.-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z]{1,6}"
    r"|[\w.-]+\.(?:py|ts|tsx|js|mjs|cjs|sh|rb|go|toml|ini|json|jsonc|ya?ml|cfg|conf|env|properties))(?![\w/-])"
)
_BARE_CALL = re.compile(r"(?<![\w`.])([A-Za-z_]\w*(?:\.\w+)*)\(\)")
_CAMEL = re.compile(r"(?<![\w`])([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+)(?![\w`])")
_VALUE = re.compile(r"^(?:\$?\d[\d.,:%]*|true|false|none|null|yes|no|on|off|\.\d+)$", re.I)
_PLACE_FILE = re.compile(
    r"^(?:.*/)?(?:Makefile|makefile|GNUmakefile|package\.json|pyproject\.toml|setup\.cfg|tox\.ini|Dockerfile[\w.-]*"
    r"|crontab|[\w.-]*\.env|\.env(?:\.[\w-]+)?|Procfile|Jenkinsfile|justfile|Taskfile\.ya?ml)$"
)
_CONFIG_SUFFIX = frozenset(
    {".toml", ".ini", ".cfg", ".conf", ".json", ".jsonc", ".yaml", ".yml", ".properties", ".env"}
)
# a tool's own command line: the switch belongs to the tool unless it runs project code
_TOOL_CMD = re.compile(
    r"`(?:sudo\s+)?(?:docker|podman|npm|npx|pnpm|yarn|bun|deno|node|pytest|pip|pip3|uv|poetry|git|kubectl|helm|terraform"
    r"|cargo|go|tsc|eslint|prettier|ruff|black|mypy|jest|vitest|playwright|curl|wget|gunicorn|uvicorn|celery"
    r"|python3?\s+-m\s+(?:pytest|pip|venv|http\.server|unittest|mypy|black|ruff))\b[^`]*`",
    re.I,
)
_TOOL_MODULES = (
    r"(?:pytest|pip|venv|unittest|mypy|black|ruff|isort|flake8|pylint|coverage|build|twine|pdb|cProfile|timeit"
    r"|trace|http\.server|json\.tool|pydoc|doctest|tox|nox|uvicorn|gunicorn|celery|django|flask)\b"
)
_PROJECT_RUN = re.compile(
    r"`?(?:python3?\s+-m\s+(?!" + _TOOL_MODULES + r")[\w.]+|node\s+(?!-)[\w./-]+|npx\s+tsx\s+[\w./-]+"
    r"|tsx\s+[\w./-]+)[^`]*`?",
    re.I,
)
_FORWARD_WORDS = re.compile(
    r"\b(?:forwards?|forwarded|passes|passed|hands?)\s+(?:(?:its|their|the|any|all|every|extra)\s+)*(?:keyword\s+)?"
    r"(?:arguments|args|kwargs|options|opts|flags|params|parameters)\b"
    r"|\bspreads?\s+(?:its|the)\s+(?:options|opts|args|props)\b"
    r"|\bpass(?:es|ed)?\s+\S+\s+through\b|\bthrough\s+(?:to\s+)?`?[\w.]+`?\s+to\b",
    re.I,
)
_ABSENT = re.compile(
    r"\b(?:has\s+no|have\s+no|doesn't\s+have|does\s+not\s+have|don't\s+have|lacks?|there's\s+no|there\s+is\s+no|no\s+such"
    r"|isn't\s+(?:there|supported|implemented|wired|available)|is\s+not\s+(?:there|supported|implemented|wired|available)"
    r"|is\s+missing|are\s+missing|doesn't\s+exist|does\s+not\s+exist|don't\s+exist|not\s+yet"
    r"|add\s+(?:one|it|that)\b(?!\s+(?:to|in|into|on)\b))",
    re.I,
)
_POSSESSION = re.compile(
    r"\b(?:supports|has|takes|accepts|honours|honors|reads|respects|understands|exposes|provides|offers|recognises"
    r"|recognizes)\b",
    re.I,
)
_ADD_TO_CALL = re.compile(
    r"\badd(?:s|ed|ing)?\s+`?--?[\w-]+`?.{0,80}?\bto\s+(?:the\s+)?`?[\w./ -]+`?\s+"
    r"(?:call|command|invocation|run|step|job|target|entry|line|script)\b",
    re.I,
)


@dataclass(frozen=True)
class V5Anchor:
    subject: Subject
    kind: str  # flag | env | kw | key
    name: str = ""
    owners: tuple = ()
    callee: str = ""  # kw written inside a call: the callable it is passed to
    pronoun: bool = False
    preds: tuple = ()


@dataclass(frozen=True)
class DualAnchor:
    subject: Subject
    first: object
    second: V5Anchor
    pronoun: bool = False
    preds: tuple = ()


def _is_place(token: str) -> bool:
    bare = token.strip("`").split(" ")[0]
    return bool(
        _CI_FILE.match(bare)
        or _COMPOSE_FILE.match(bare)
        or _ENV_TEMPLATE.match(bare)
        or _PLACE_FILE.match(bare)
    )


def _config_file(token: str) -> bool:
    bare = token.strip("`").split(" ")[0]
    return PurePosixPath(bare).suffix.lower() in _CONFIG_SUFFIX and not _CI_FILE.match(bare)


_PLACE_PREP = re.compile(
    r"(?:\b(?:in|into|inside|within|where|from)\s+(?:the\s+|our\s+|its\s+)?(?:[\w-]+\s+){0,2})$", re.I
)


_HOME_BEFORE_IN = re.compile(
    r"(?:`[^`]+`|\b(?:option|flag|setting|switch|mode|toggle|key|variable|var|argument|arg|parameter|param|kwarg"
    r"|property|field)s?)"
    r"\s+(?:in|inside|within|from)\s+(?:the\s+)?$",
    re.I,
)


def _is_after_place(text: str, start: int) -> bool:
    window = text[max(0, start - 60):start]
    if _PLACE_PREP.search(window[-40:]) is None:
        return False
    # "the `--totals` flag in `report.py`", "`RateLimiter` in `limiter.py`": the switch's or the owner's home,
    # not a place
    return _HOME_BEFORE_IN.search(window) is None


def _owner_tokens(text: str, skip: set[str]) -> list[Subject]:
    """Owner candidates in a sentence: own words, backticked code, bare paths/calls/classes, "the X";
    tokens after a place word ("in `f()`", "where `X` builds") are places, not owners."""
    out: list[Subject] = []
    if _OWN.search(text):
        out.append(Subject("own", phrase=" ".join(text.lower().split()[:6])))
    for m in _BACKTICK.finditer(text):
        inner = m.group(1).strip()
        if _is_after_place(text, m.start()) and not _config_file(inner):
            continue  # a config file after "in" still owns its keys (checked in _v5_keeps)
        run = re.match(r"(?:python3?\s+-m\s+([\w.]+)|node\s+([\w./-]+)|(?:npx\s+)?tsx\s+([\w./-]+))", inner)
        if run:
            head = next(g for g in run.groups() if g)
        else:
            head = re.split(r"[\s(=:,]", inner.lstrip("@"), maxsplit=1)[0]
        if not head or head in skip or head.lstrip("-") in skip or _VALUE.match(head) or head.startswith("-"):
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9_]+(?:=.*)?", head):
            continue  # an env name is a switch, not an owner
        if "=" in inner and "(" not in inner and not run:
            continue
        call = re.match(r"@?([A-Za-z_][\w.]*)\(", inner)
        token = (call.group(1) + "()") if call else head
        out.append(Subject("token", token=token.rstrip(".,;:'"), backticked=True))
    for pattern in (_BARE_PATH, _BARE_CALL, _CAMEL):
        for m in pattern.finditer(text):
            tok = m.group(1)
            if tok in skip or (
                _is_after_place(text, m.start()) and not (pattern is _BARE_PATH and _config_file(tok))
            ):
                continue
            out.append(
                Subject("token", token=tok + ("()" if pattern is _BARE_CALL else ""), backticked=False)
            )
    for m in _THE_X.finditer(text):
        if _is_after_place(text, m.start()):
            continue
        words = " ".join(w for w in m.groups() if w)
        out.append(Subject("generic", phrase=words))
    return out


def _switches(P, s: str) -> list[tuple[int, str, str, str]]:
    """(offset, name, kind, callee) for the switch tokens of one sentence."""
    found: dict[str, tuple[int, str, str, str]] = {}

    def put(off: int, name: str, kind: str, callee: str = "") -> None:
        if name and name not in found and not P._external(name) and not _fixed_external(name):
            found[name] = (off, name, kind, callee)

    tool_spans = [m.span() for m in _TOOL_CMD.finditer(s) if not _PROJECT_RUN.fullmatch(m.group(0))]

    def in_tool(off: int) -> bool:
        return any(a <= off < b for a, b in tool_spans)

    for m in _CALL_KW.finditer(s):
        for kw in re.finditer(r"(?<![\w.\-\"'])([a-z_][A-Za-z0-9_]{2,})\s*=(?!=)", m.group(2)):
            put(m.start(2) + kw.start(1), kw.group(1), "kw", m.group(1))
    for m in P._FLAG.finditer(s):
        if not in_tool(m.start(1)):
            put(m.start(1), m.group(1), "flag")
    for m in _ENV_ASSIGN.finditer(s):
        if not P._WELL_KNOWN_ENV.match(m.group(1)) and not in_tool(m.start(1)):
            put(m.start(1), m.group(1), "env")
    for m in _KW_ASSIGN.finditer(s):
        name, op = m.group(1), m.group(2)
        span = m.group(0)
        if re.match(r"`\s*[A-Z][A-Z0-9_]+=", span) or in_tool(m.start(1)):
            continue
        kind = "key" if (op == ":" and not re.search(r"[{(]", span)) or re.search(r"\s=\s", span) else "kw"
        put(m.start(1), name, kind)
    if _CONFIG_NAMED.search(s):
        for m in _QUOTED_KEY.finditer(s):
            if not in_tool(m.start(1)):
                put(m.start(1), m.group(1), "key")
    for m in _NOUNED.finditer(s):
        name, phrase = m.group(1), m.group(0)
        if name.startswith("--"):
            continue
        if _ENV_NOUN.search(phrase) or re.fullmatch(r"[A-Z][A-Z0-9_]+", name):
            kind = "env"
        elif _KEY_NOUN.search(phrase):
            kind = "key"
        else:
            kind = "kw"
        put(m.start(1), name, kind)
    for m in _SET_TO.finditer(s):
        put(m.start(1), m.group(1), "key")
    return sorted(found.values())


_EXTERNAL_SERVICE = re.compile(
    r"\b(?:the|their|its|a|an)\s+(?:[\w-]+\s+){0,2}(?:api|service|server|provider|vendor|platform|gateway|upstream"
    r"|third[- ]party|saas)"
    r"(?:'s)?\s+(?:takes|accepts|expects|requires|reads|honou?rs|supports|has|uses|wants|needs|sends|returns)\b",
    re.I,
)
# today's _BUILDS minus "new" and possessive "has/have/with support for" (they assert, they do not build)
_V5_BUILDS = re.compile(
    r"\b(?:implement\w*|introduc\w*|add\s+support|(?<!\bhas\s)(?<!\bhave\s)(?<!\bwith\s)support\s+for|should|must"
    r"|needs?\s+to|has\s+to|have\s+to|build\w*|teach|wire\s+up|hook\s+up|make\s+(?:it|sure))\b",
    re.I,
)
_POLITE = re.compile(
    r"\b(?:could|would|will|can)\s+you\b|\bwould\s+(?:be\s+)?(?:great|nice|helpful|appreciated)\b"
    r"|\bwould\s+appreciate\b",
    re.I,
)


_PLACE_PHRASE = re.compile(
    r"\bdocker-compose[\w.-]*\b|\bdocker\s+compose\s+file\b|\b(?:the\s+)?(?:production\s+|prod\s+|dev\s+)?dockerfile\b"
    r"|\bmakefile(?:'s)?\b|`make\s+[\w:-]+`"
    r"|\b[\w.-]+\.service\b|\b(?:npm|yarn|pnpm|bun)\s+(?:run\s+\S+|scripts?)\b"
    r"|\b(?:the\s+)?`[^`]+`\s+(?:npm|yarn|pnpm)\s+scripts?\b"
    r"|\bpackage\.json(?:'s)?\s+`?[\w:-]+`?\s+scripts?\b",
    re.I,
)
_V5_FUTURE = re.compile(
    r"\b(?:we|i|you|they)(?:'ll|\s+will|\s+shall|\s+are\s+going\s+to|\s+plan\s+to|\s+intend\s+to)\b"
    r"|\bonce\s+(?:it|we|that|this|the\s+\w+)\s+(?:supports?|has|have|accepts?|reads?|is\s+added|lands?|ships?)\b"
    r"|\b(?:later|eventually|in\s+the\s+future|next\s+(?:week|sprint|release))\b",
    re.I,
)


def _tool_named(P, s: str) -> bool:
    text = _PLACE_PHRASE.sub(" ", _PROJECT_RUN.sub(" ", s))
    return bool(P._TOOL_NAMED.search(text) or _TOOL_NOUNS.search(text))


_SECRET_ENV = re.compile(
    r"(?:API_?KEY|_KEY|_TOKEN|_SECRET|_PASSWORD|_PASSWD|_DSN|_URL|_URI|_HOST|_PORT|_ENDPOINT|_REGION|_BUCKET)$"
)


def _LIB_IN_SENTENCE(s: str) -> bool:
    for m in _BACKTICK.finditer(s):
        inner = m.group(1).strip()
        root = re.split(r"[.(\s]", inner, maxsplit=1)[0]
        if "." in inner.split("(")[0] and root.islower() and root in _STD_ROOTS:
            return True
    return bool(
        re.search(
            r"\b(?:we|i)\s+(?:use|added|adopted|rely\s+on)\s+`?[\w.@/-]+`?(?:'s)?\s*(?:module|library|package|sdk|client)?",
            s,
            re.I,
        )
        or re.search(
            r"\b(?:"
            + "|".join(sorted(_STD_ROOTS))
            + r")(?:'s)?\s+(?:option|parameter|argument|kwarg|setting|flag)s?\b",
            s,
        )
    )


_OWN_SERVICE = re.compile(r"\b(?:our|my|the\s+project's)\s+(?:[\w-]+\s+){0,2}(?:api|service|server)\b", re.I)
_LIB_PREV = re.compile(
    r"\b(?:we|i)\s+(?:use|used|rely\s+on|added|depend\s+on|call)\s+(?:the\s+(?:standard\s+)?)?(?:`[^`]+`"
    r"|[A-Za-z][\w.-]*)(?:'s)?(?:\s+(?:module|library|package|client|sdk))?",
    re.I,
)


def _external_dotted(token: str) -> bool:
    """`yaml.safe_dump`, `os.getenv`, `requests.get`: a member of a module that is not a project path."""
    bare = token.removesuffix("()")
    if "." not in bare or "/" in bare:
        return False
    root = bare.split(".", 1)[0]
    return root.islower() and root in _STD_ROOTS


_STD_ROOTS = frozenset(("""os sys re json yaml toml tomllib csv io fs path pathlib requests httpx urllib
subprocess shutil aiohttp flask django fastapi sqlalchemy pydantic click typer rich jinja2 boto botocore
stripe openai anthropic express react vue next zod prisma knex pino winston dayjs moment""" + """
datetime time logging sqlite3 random math itertools functools collections typing asyncio http https crypto
zlib gzip child_process process url util stream buffer events dateutil numpy np pandas pd boto3 redis psycopg2
axios lodash
""").split())


_BUILD_VERB = re.compile(
    r"(?:^|[.;:!?(\u2014\u2013-]\s*|\b(?:please|then|also|and|first|now|just|so)\s+"
    r"|\b(?:can|could|would|will)\s+you\s+(?:please\s+)?)"
    r"(?:add|create|implement|introduce|build|write|define|declare|generate|expose|teach|wire\s+up|give|extend|let|allow"
    r"|have|support|rename)\b"
    r"(?!\s+(?:it|that|this|them)\s+(?:to|in|into|on)\b)",
    re.I,
)


_MAKE_BUILD = re.compile(
    r"\bput\s+(?:it|this|that|them)\s+behind\s+(?:a|an)\b|\b(?:i'?d|we'?d)\s+like\b|\bit'?d\s+be\s+(?:great|nice)\s+if\b"
    r"|\b(?:update|change|modify|extend|allow|give|need\s+to\s+teach)\s+(?:\S+\s+){0,5}?(?:to\s+|so\s+(?:it|that\s+it)\s+)?"
    r"(?:accept|accepts|take|takes|handle|handles|read|reads|honou?r|honou?rs|support|supports|have|has|recogni[sz]e"
    r"|understand|parse)\b"
    r"|\b(?:make|have|let|get|teach)\s+(?:\S+\s+){0,5}?(?:read|reads|accept|accepts|take|takes|support|supports"
    r"|honou?r|honou?rs"
    r"|respect|respects|recogni[sz]e|recogni[sz]es|handle|handles|understand|understands|parse|parses|expose|exposes"
    r"|check|checks)\b",
    re.I,
)
_RENAME = re.compile(
    r"\brenam(?:e|es|ed|ing)\b|\b(?:now|from\s+now\s+on)\s+(?:called|named)\b|\bcall\s+it\s+`|\bis\s+`[^`]+`\s+now\b",
    re.I,
)
_MAKE_USE = re.compile(
    r"\bmake\s+(?:\S+\s+){0,5}?(?:call|calls|run|runs|use|uses|invoke|invokes|pass|passes)\b", re.I
)


def _creating(P, span: str) -> bool:
    """Creation or absence wording; possession verbs assert, they do not create ("supports a `x` key");
    "add `--x` to <an invocation>" passes a switch (neutralised first)."""
    if _ABSENT.search(span) or _MAKE_BUILD.search(span) or _RENAME.search(span):
        return True
    neutral = _POSSESSION.sub("has", span)
    neutral = _ADD_TO_CALL.sub(" ", neutral)
    neutral = _ADD_TO_PLACE.sub(lambda m: m.group(0) if _keeps_creation(P, m) else " ", neutral)
    if _BUILD_VERB.search(neutral):
        return True
    return _creates(P, neutral)


_BUILD_GOV = re.compile(
    r"(?:(?:^|[.;:!?(\u2014\u2013]\s*|\b(?:please|then|also|and|first|now|just|so|to)\s+"
    r"|\b(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|\b(?:should|must|needs?\s+to|has\s+to|have\s+to|ought\s+to)\s+)"
    r"(?:add|create|implement|introduce|build|write|define|declare|generate|expose|teach|wire\s+up|give|extend|support"
    r"|accept|take|handle|read|honou?r|have|recogni[sz]e|understand|parse)"
    r"|\b(?:we|i)\s+(?:need|want|would\s+like|'d\s+like)\b"
    r"|\bmake\s+(?:\S+\s+){0,5}?(?:accept|take|read|support|honou?r|handle|understand|parse|recogni[sz]e)"
    r"|\b(?:update|change|modify|extend|allow|let|give)\s+(?:\S+\s+){0,5}?(?:to\s+|so\s+(?:that\s+)?it\s+)?"
    r"(?:accepts?|takes?|handles?|reads?|honou?rs?|supports?|have|has|recogni[sz]es?|understands?|parses?)"
    r"|\bput\s+(?:it|this|that|them)\s+behind\s+(?:a|an)|\bit'?d\s+be\s+(?:great|nice)\s+if|\b(?:i|we)'?d\s+(?:like|love)"
    r"|\brenam\w*|\bnow\s+(?:called|named)|\bcall\s+it)\b[^.;!?]*$",
    re.I,
)
_ABSENT_BEFORE = re.compile(
    r"(?:\bno\s+(?:such\s+)?|\bhas\s+no\s+|\bhave\s+no\s+|\bwithout\s+(?:a|an|the|any)\s+|\bthere(?:'s|\s+is)\s+no\s+"
    r"|\blacks?\s+(?:a|an|the)?\s*)(?:[\w-]+\s+){0,1}$",
    re.I,
)
_ABSENT_AFTER = re.compile(
    r"^[`'\"]?\s*(?:(?:flag|option|setting|key|variable|switch|kwarg|argument|parameter|env\s+var)\s+)?"
    r"(?:(?:doesn'?t|does\s+not|isn'?t|is\s+not|don'?t|aren'?t|are\s+not)\s+(?:exist|there|supported|implemented"
    r"|available|wired|defined|recogni[sz]ed|accepted|read|known)"
    r"|(?:is|are)\s+missing|(?:is|are)\s+not\s+yet)",
    re.I,
)


# the next sentence refers back to the switch and says it is missing or to be built: "The flag doesn't
# exist yet; add it."
_FOLLOW_ABSENT = re.compile(
    r"^\W*(?:(?:the|that|this)\s+(?:flag|option|setting|switch|key|variable|argument|parameter|env\s+var)|it|that|this)"
    r"\b[^.;!?]{0,80}?"
    r"\b(?:doesn'?t\s+exist|does\s+not\s+exist|isn'?t\s+(?:there|implemented|supported|wired|available)"
    r"|is\s+not\s+(?:there|implemented|supported|wired|available)"
    r"|is\s+missing|(?:is|are)\s+not\s+yet|is\s+new|needs\s+to\s+be\s+(?:added|built|created)"
    r"|has\s+to\s+be\s+(?:added|built))"
    r"|^\W*(?:so\s+|then\s+|please\s+|just\s+)?add\s+(?:it|one|that)\b",
    re.I,
)


def _created_local(P, s: str, off: int, name: str) -> bool:
    """v5.1: creation or absence that governs THIS switch (code spans blanked, offsets kept)."""
    for m in _ADD_TO_PLACE.finditer(s):
        if m.start() <= off < m.end() and not _keeps_creation(P, m):
            return False  # "add `--x` to <an invocation>" passes the switch
    blank = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), s)
    before = blank[max(0, off - 120):off].rstrip("`'\" ")
    after = s[off + len(name):off + len(name) + 60]
    if _BUILD_GOV.search(before + " "):
        return True
    if _ABSENT_BEFORE.search(before + " ") or _ABSENT_AFTER.match(after):
        return True
    if _WIRE_AFTER.match(blank[off + len(name):off + len(name) + 140]):
        # "Set `X=10` in .env.example and read it in `fetch_rates`": the request asks to build the read
        return True
    if _FROM_ENV_BUILD.search(before + " "):  # noqa: SIM103 - the prototype's form
        # "Default the currency to the `X` env var", "read the timeout from the `X` variable": builds the read
        return True
    return False


_FROM_ENV_BUILD = re.compile(
    r"\b(?:default|defaults|defaulting|fall\s+back|falls\s+back|read|reads|take|takes|load|loads|get|gets|pull|pulls"
    r"|source|configure)\b"
    r"[^.;!?]{0,80}?\b(?:to|from|via|through|with)\s+(?:the\s+|a\s+|an\s+)?$",
    re.I,
)
_WIRE_AFTER = re.compile(
    r"^[^.;!?]{0,100}?\b(?:and|then|,)\s+(?:also\s+)?(?:make\s+\S+\s+)?(?:read|reads|load|loads|parse|parses|honou?r"
    r"|honou?rs|wire|plumb|thread|hook\s+up|pick\s+up|respect)"
    r"\s+(?:it|them|that|this|the\s+(?:value|setting|flag|option|variable|key))\b",
    re.I,
)


def _used_switch(P, prompt: str):
    sents = [s for _, s in P._sentences(prompt or "")]
    out = []
    # a name built or declared missing anywhere in the request is created, wherever it is used
    absent: set[str] = set()
    for idx, s in enumerate(sents):
        neutral = _MAKE_USE.sub(
            " use ", _ADD_TO_PLACE.sub(lambda m: m.group(0) if _keeps_creation(P, m) else " use ", s)
        )
        follow = sents[idx + 1] if idx + 1 < len(sents) else ""
        whole = bool(P._CREATING_SENTENCE.search(neutral)) or bool(_FOLLOW_ABSENT.search(follow))
        for off, name, _k, _c in _switches(P, s):
            if whole or _created_local(P, s, off, name):
                absent.add(name)
    for i, s in enumerate(sents):
        prev = sents[i - 1] if i else ""
        nxt = sents[i + 1] if i + 1 < len(sents) else ""
        sw = _switches(P, s)
        if not sw:
            continue
        if not (_USE.search(s) or _USE.search(nxt)):
            continue
        if _V5_FUTURE.search(s):
            continue  # "We'll pass `--dry-run` to the deploy script once it supports it"
        if _FORWARD_WORDS.search(s + " " + nxt):
            continue  # the request itself says the option is passed through to something else
        names = {name for _, name, _, _ in sw} | {name.lstrip("-") for _, name, _, _ in sw}
        head = _subject(s)
        if head.kind == "pronoun" and prev and _LIB_PREV.search(prev):
            continue  # "We use `requests` ... It stops ... when given `x=...`": the library's option
        if head.kind == "token" and _external_dotted(head.token):
            continue  # "`yaml.safe_dump` keeps ... when given `sort_keys=False`"
        if _EXTERNAL_SERVICE.search(s) and not _OWN_SERVICE.search(s):
            # "the partner API takes its key as …" (but "our API" / "our <x> service" are the project's)
            continue
        owners = _owner_tokens(s, names) + _owner_tokens(nxt, names) + _owner_tokens(prev, names)
        for _off, name, kind, callee in sw:
            if name in absent:
                continue
            if (
                kind == "env"
                and not re.match(r"\s*=", s[_off + len(name):_off + len(name) + 3])
                and not _POSSESSION.search(prev + " " + s)
            ):
                # "Use the `X` env var for …" introduces a variable (premise.py: "the X environment variable")
                continue
            if not callee and _tool_named(P, s):
                # v4.2's whole-sentence tool guard, every kind (project runs `python -m <pkg>` / `node <path>`
                # blanked)
                continue
            if kind in ("kw", "key") and not callee and _LIB_IN_SENTENCE(s):
                continue  # a library or SDK named in the sentence owns its options
            if kind == "env" and _SECRET_ENV.search(name):
                # credentials and endpoints configure services; a switch premise is a behaviour switch
                continue
            clause = P._clause(s, _off, len(name)) if hasattr(P, "_clause") else s
            if _V5_BUILDS.search(_CODE_SPANS.sub(" ", clause)):
                continue  # today's build words in the switch's own clause ("should", "must", "new", ...)
            if callee:  # noqa: SIM108 - the prototype's form
                own = (Subject("token", token=callee + "()", backticked=True),)
            else:
                own = tuple(owners)
            if not own:
                continue
            keys = tuple(
                dict.fromkeys((name, name.lstrip("-"), name.lstrip("-").replace("-", "_"), *_variants(name)))
            )
            a = P.Assertion(name, {"flag": "flag", "env": "env"}.get(kind, "name"), keys, existing=True)
            out.append((a, V5Anchor(subject=own[0], kind=kind, owners=own, callee=callee, name=name)))
    return out


def _read_by_code(token: str, ctx) -> bool:
    """A config file is the project's when a non-test code file names it (path or base name)."""
    bare = token.strip("`").split(" ")[0]
    base = PurePosixPath(bare).name
    for rel in ctx.code_files():
        text = ctx.text(rel) or ""
        if base and base in text:
            return True
    return False


def _basename_owner(subj: Subject, ctx) -> Subject | None:
    tok = subj.token
    if "/" in tok or not PurePosixPath(tok).suffix:
        return None
    hits = [f for f in ctx.all_files if PurePosixPath(f).name == tok]
    return Subject("token", token=hits[0], backticked=True) if len(hits) == 1 else None


def _library_kwarg(name: str, prompt: str, ctx) -> bool:
    """v5.2 precision filter (applies to every noted name, today's rule included): `name=value` handed to a
    function the project does not define ("pass `pool_pre_ping=True` to create_engine"), or under
    forwarding wording ("open_db() already forwards keyword args to sqlite3.connect, so pass
    check_same_thread=False")."""
    bare = name.split("=", 1)[0]
    for s in [x for _, x in P_SENT(prompt)]:
        if not re.search(rf"(?<![\w-]){re.escape(bare)}\s*=", s):
            continue
        if _FORWARD_WORDS.search(s) or re.search(
            r"\bforwards?\s+(?:\w+\s+){0,2}(?:keyword\s+)?(?:args|arguments|kwargs|options)\b", s, re.I
        ):
            return True
        m = re.search(
            rf"(?<![\w-]){re.escape(bare)}\s*=\s*\S+\s+(?:to|into|on)\s+`?([A-Za-z_][\w.]*)`?(?:\(\))?", s
        )
        if m:
            callee = m.group(1)
            root = callee.split(".", 1)[0]
            last = callee.rpartition(".")[2]
            if not ctx.defs(last) and not _project_owned(Subject("token", token=root, backticked=True), ctx):
                return True
    return False


def P_SENT(prompt: str):
    from truthstone.intent import premise as _P

    return _P._sentences(prompt or "")


def _project_prefixed(name: str, ctx) -> bool:
    bare = name.split("=", 1)[0]
    if not re.fullmatch(r"[A-Z][A-Z0-9]*_[A-Z0-9_]+", bare):
        return False
    prefix = bare.split("_", 1)[0].lower()
    names = {n.lower().replace("-", "").replace("_", "") for n in ctx.project_names()}
    return bool(prefix) and prefix in names


def _v5_keeps(anchor: V5Anchor, ctx) -> bool:
    if anchor.callee and "." in anchor.callee:
        root = anchor.callee.split(".", 1)[0].lstrip("@")
        if root in ("self", "this", "cls") or not _project_owned(
            Subject("token", token=root, backticked=True), ctx
        ):
            return False  # `stripe.Charge.create(idempotency_key=...)`: the option belongs to the library
    if anchor.kind in ("env", "key") and _project_prefixed(anchor.name, ctx):
        return True  # `CLINICQ_TZ`, `KILNLOG_UNITS`: named after the project itself
    owned = []
    for subj in anchor.owners:
        if anchor.kind == "key" and subj.kind in ("own", "generic"):
            continue  # a key is owned by the code or the config file that reads it, not by "our <site>"
        if subj.kind == "own":
            owned.append(subj)
            continue
        if subj.kind == "generic":
            if _generic_files(subj, ctx):
                owned.append(subj)
            continue
        tok = subj.token
        if _is_place(tok):
            continue  # a place where a switch is passed or set, never its owner ...
        if _config_file(tok):
            if anchor.kind == "key" and _project_owned(subj, ctx) and _read_by_code(tok, ctx):
                owned.append(subj)  # ... except a project config file that project code reads, for its keys
            continue
        alt = _basename_owner(subj, ctx)
        if alt is not None:
            subj = alt
        if _project_owned(subj, ctx):
            owned.append(subj)
    if not owned:
        return False
    return not any(o.kind != "own" and _forwards(o, ctx, _definition_forwards_v51) for o in owned)


_ADD_TO_PLACE = re.compile(
    r"\badd(?:s|ed|ing)?\s+(?P<what>`[^`\n]+`|--?[\w-]+)(?P<mid>[^.;!?]{0,80}?)\bto\s+"
    r"(?P<place>(?:the\s+)?(?:`[^`\n]+`|[\w./:-]+)(?:\s+[\w:'-]+){0,3})",
    re.I,
)
_INVOCATION_WORD = re.compile(
    r"\b(?:call|command|invocation|run|step|job|target|entry|line|script|cron|crontab|dockerfile|makefile|workflow"
    r"|pipeline)\b",
    re.I,
)
_PARSER_WORD = re.compile(
    r"\b(?:parser|argparse|argument\s+parser|cli\s+definition|options?\s+(?:list|table)|schema)\b", re.I
)


def _keeps_creation(P, m) -> bool:
    place = m.group("place")
    if _PARSER_WORD.search(place):
        return True
    mpath = re.search(r"`([^`\n]+)`|([\w./-]+\.\w+)", place)
    if mpath:
        path = (mpath.group(1) or mpath.group(2)).split()[0]
        if _source_file(P, path) and not _INVOCATION_WORD.search(place[mpath.end():]):
            return True
    return False


def _neutral_prompt(P, prompt: str) -> str:
    """For `_created`: "add `--x` to the `tool.py` call / the Makefile target / the Dockerfile" passes a
    switch (use); "add `--x` to the parser / to `src/cli.py`" builds it (creation stays)."""
    return _POSSESSION.sub(
        "has", _ADD_TO_PLACE.sub(lambda m: m.group(0) if _keeps_creation(P, m) else " ", prompt)
    )


def _definition_forwards_v51(text: str, name: str, rel: str) -> bool:
    n = re.escape(name)
    if rel.endswith((".py", ".pyi", ".pyx")):
        return _definition_forwards(text, name, rel)
    heads = (
        rf"\bfunction\s*\*?\s*{n}\s*(?:<[^>]*>)?\s*\(",
        rf"\b(?:const|let|var)\s+{n}\s*(?::[^=\n]+)?=\s*(?:async\s*)?(?:function\s*)?\(",
        rf"^\s*(?:async\s+)?{n}\s*\(",
    )
    for head in heads:
        for m in re.finditer(head, text, re.M):
            params, end = _balanced(text, m.end() - 1)
            names = [p for p in re.findall(r"(?:^|,)\s*(?:\.\.\.)?\s*\{?\s*([A-Za-z_$][\w$]*)", params) if p]
            body = text[end:end + 3000]
            for p in names:
                pe = re.escape(p)
                # spread or passed whole INTO another call: f(...p), f(a, { ...p }), f(a, p)
                if re.search(rf"[\w$.]+\s*\([^;]*?(?:\.\.\.\s*{pe}\b|\{{[^}}]*\.\.\.\s*{pe}\b)", body):
                    return True
            if _NODE_FORWARD.search(body):
                return True
    return False


def _c1_dual(P, prompt: str, base_names: set[str]):
    """v5.2's ``_c1``: v4.3's names, then the used-switch rule's; a name both assert gets both anchors."""
    out = _c1(P, prompt, base_names)
    index = {a.name: k for k, (a, _) in enumerate(out)}
    used = _used_switch(P, prompt)
    # v5.1: v5's names use the local rule inside _used_switch, not the 4-word window
    created: set[str] = set()
    seen = set(base_names)
    for a, anchor in used:
        if a.name in seen or a.name in created or a.name.lstrip("-") in created:
            continue
        seen.add(a.name)
        if a.name in index:
            k = index[a.name]
            old_a, old_anchor = out[k]
            out[k] = (
                old_a,
                DualAnchor(
                    subject=old_anchor.subject,
                    first=old_anchor,
                    second=anchor,
                    pronoun=getattr(old_anchor, "pronoun", False),
                    preds=getattr(old_anchor, "preds", ()),
                ),
            )
        else:
            out.append((a, anchor))
    return out


def _keeps_note_dual(anchor, ctx) -> bool:
    """v5.2's ``_keeps_note``: with v5.2 installed, v4.3's own test reads definitions through
    ``_definition_forwards_v51`` too."""
    if isinstance(anchor, DualAnchor):
        first = anchor.first
        if getattr(first, "pronoun", False) and _external_object(getattr(first, "preds", ()), ctx):
            return False  # v4.3's library-pronoun verdict is not overridden
        return _keeps_note(first, ctx, _definition_forwards_v51) or _v5_keeps(anchor.second, ctx)
    if isinstance(anchor, V5Anchor):
        return _v5_keeps(anchor, ctx)
    return _keeps_note(anchor, ctx, _definition_forwards_v51)


_WHOLE_ENV = re.compile(
    r"\*\*\s*os\.environ|env\s*=\s*os\.environ|dict\(\s*os\.environ|os\.environ\.copy\(\)|\.\.\.\s*process\.env"
)


def _env_read_by_name(name: str, ctx) -> bool:
    """True when some non-doc file spells the name (or a case variant), or code reads it by a prefix it
    starts with."""
    keys = {name, name.lower()}
    prefixes = set()
    parts = name.split("_")
    for k in range(1, len(parts)):
        prefixes.add("_".join(parts[:k]) + "_")
    for rel in ctx.all_files:
        from truthstone.validate import spec_integrity

        if spec_integrity.is_doc_path(rel):
            continue
        text = ctx.text(rel) or ""
        if any(k in text for k in keys):
            return True
        if any(re.search(rf"[\"']{re.escape(p)}(?:\{{|[\"'])", text) for p in prefixes):
            return True  # a prefix read: f"FEED_{key}" / startswith("FEED_")
        for m in re.finditer(
            r"(?:auto_envvar_prefix|env_prefix)\s*[=:]\s*[\"']([A-Za-z][A-Za-z0-9_]*)[\"']", text
        ):
            if name.upper().startswith(m.group(1).upper().rstrip("_") + "_"):
                return True  # Click auto_envvar_prefix / pydantic env_prefix read every PREFIX_* name
    return False


# == the integration (the prototypes' install()) ===================================================


def _keeps_note_v43(anchor, ctx) -> bool:
    """v4.3's ``_keeps_note`` as v4.3 alone runs it (its own ``_definition_forwards``)."""
    return _keeps_note(anchor, ctx, _definition_forwards)


def _assertions_v43(P, prompt: str, c1):
    """v4.3's ``assertions``: today's assertions plus this rule's names (other callers:
    premise_unmet, the engine's ``again``); keys carry the case variants, as in v4.1."""
    prompt = (prompt or "").translate(_APOS)
    base = P._today_assertions(prompt)
    for a, _anchor in c1(P, prompt, {b.name for b in base}):
        base.append(
            P.Assertion(a.name, a.kind, tuple(dict.fromkeys(a.keys + _variants(a.name))), existing=True)
        )
    return base


def _assertions_v52(P, prompt: str):
    """v5.2's ``assertions``: other callers (premise_unmet's Stop backstop, the engine's `again`)
    never get names only the used-switch rule asserts: those are judged at prompt time with their
    ownership test (comp-3-4)."""
    out = _assertions_v43(P, prompt, _c1_dual)
    try:
        pr = (prompt or "").translate(_APOS)
        base_names = {b.name for b in P._today_assertions(pr)}
        v5_only = {a.name for a, an in _c1_dual(P, pr, base_names) if isinstance(an, V5Anchor)}
        return [a for a in out if a.name not in v5_only]
    except Exception:  # noqa: BLE001 - the prototype's fail-open: v4.3's names stand
        return out


def assertions(P, prompt: str):
    """The names ``prompt`` asserts exist, for ``premise.assertions``: v5.2's when the used-switch
    rule speaks, v4.3's otherwise. Neither returns a name only the used-switch rule asserts."""
    if USED_SWITCH_SPEAKS:
        return _assertions_v52(P, prompt)
    return _assertions_v43(P, prompt, _c1)


def _check_v43(P, prompt, root, files, already, c1, keeps_note):
    """v4.3's ``check``, with the ``_c1`` and ``_keeps_note`` its install finds in place."""
    if files is None or not prompt:
        return P.Premise()
    prompt = prompt.translate(_APOS)
    files = list(files)
    base = P._today_assertions(prompt)
    c1_names = c1(P, prompt, {a.name for a in base})
    anchors = {a.name: anchor for a, anchor in c1_names}
    asserted = base + [a for a, _ in c1_names]
    asserted = [a for a in asserted if not already or a.name not in already]
    if asserted:
        packages = P._packages(root, prompt)
        if packages:
            asserted = [a for a in asserted if not P.library_api(a.name, prompt, packages)]
    if not asserted:
        return P.Premise()
    ctx = _Ctx(P, root, files, prompt)
    # rd1-2-9: the wider code suffixes (and C1b's "symbol" switch kind) for premise resolution only;
    # premise_unmet, which shares ``_code_file``, never sees them.
    unbacked = P.resolve(
        asserted,
        Path(root),
        files,
        code_suffixes=frozenset(P._CODE_SUFFIXES | _EXTRA_SUFFIXES),
        switch_kinds=frozenset(P._SWITCH_KINDS | {"symbol"}),
    )
    scan_complete = ctx.scan_complete() if any(a.kind == "symbol" and only for a, only in unbacked) else True
    kept = []
    for a, only in unbacked:
        anchor = anchors.get(a.name)
        if anchor is not None:
            if _variant_resolves(a, anchor, ctx):
                continue
            if only:
                subject_files = _subject_files(anchor, ctx)
                if not all(_note_file(p, subject_files) for p in only):
                    continue  # something reads it
        if (
            only
            and a.kind == "symbol"
            and not (scan_complete and all(_HISTORY.match(PurePosixPath(p).name) for p in only))
        ):
            continue  # C1b: an asserted symbol only in history files, when every code file was read
        kept.append((a, only))
    missing, only_in = [], {}
    for a, only in kept:
        anchor = anchors.get(a.name)
        if anchor is not None and not keeps_note(anchor, ctx):
            continue  # after resolve, only for names still missing (rd1-2-13)
        missing.append(a)
        if only:
            only_in[a.name] = only
    return P.Premise(missing=missing, only_in=only_in)


def _env_pass(P, res, prompt, root, files, already):
    """v5.1's second pass: a used env switch no file but docs spells and the project owns."""
    try:
        if files is None or not prompt:
            return res
        have = {a.name for a in res.missing}
        used = [
            (a, an)
            for a, an in _used_switch(P, (prompt or "").translate(_APOS))
            if an.kind == "env" and a.name not in have
        ]
        if not used:
            return res
        ctx = _Ctx(P, root, list(files), prompt)
        for a, an in used:
            if already and a.name in already:
                continue
            if not _env_read_by_name(a.name, ctx) and _v5_keeps(an, ctx):
                res.missing.append(a)
    except Exception:  # noqa: BLE001 - fail open, as the prototype does
        return res
    return res


def _precision_filter(P, res, prompt, root, files):
    """v5.2's final precision filter, on every noted name: a library's keyword argument is not the
    project's switch (``_library_kwarg``)."""
    try:
        if not res.missing or files is None:
            return res
        ctx = _Ctx(P, root, list(files), prompt)
        keep = [a for a in res.missing if not _library_kwarg(a.name, (prompt or "").translate(_APOS), ctx)]
        if len(keep) != len(res.missing):
            dropped = {a.name for a in res.missing} - {a.name for a in keep}
            res.missing[:] = keep
            for n in dropped:
                res.only_in.pop(n, None)
    except Exception:  # noqa: BLE001 - fail open, as the prototype does
        return res
    return res


def _check_v52(P, prompt, root, files, already):
    """v5.2's ``check``: v4.3's with the used-switch names, the env pass, the final filter."""
    res = _check_v43(P, prompt, root, files, already, _c1_dual, _keeps_note_dual)
    res = _env_pass(P, res, prompt, root, files, already)
    return _precision_filter(P, res, prompt, root, files)


def check(P, prompt, root, files, already=None):
    """The premise check for ``premise.check``. With the used-switch rule speaking, v5.2's result.
    Otherwise v4.3's (today's rule, v4.3, C1b, C1c) after v5.2's final filter, with what v5.2 would
    note beyond it on ``recorded``. Day 6: then the switches the request relies on that nothing reads
    (``premise_names``, C7), beside them."""
    if USED_SWITCH_SPEAKS:
        return _relied_pass(P, _check_v52(P, prompt, root, files, already), prompt, root, files, already)
    if files is not None:
        files = list(files)  # read by both paths
    spoken = _precision_filter(
        P, _check_v43(P, prompt, root, files, already, _c1, _keeps_note_v43), prompt, root, files
    )
    full = _check_v52(P, prompt, root, files, already)
    names = {a.name for a in spoken.missing}
    spoken.recorded = [a for a in full.missing if a.name not in names]
    return _relied_pass(P, spoken, prompt, root, files, already)


# Day 6 (C7): whether the relied-switch rule's names are noted (True) or left out (False).
RELIED_SPEAKS = True


def _relied_pass(P, res, prompt, root, files, already):
    """C7 (``premise_names.relied``): a switch-like name the request gives a value, uses, or names as where
    present behaviour comes from, that the request does not ask to make, that no other program owns, and
    that nothing in the repository reads, joins the noted names. Fail-open: a rule that cannot run adds
    nothing."""
    if not RELIED_SPEAKS or files is None or not prompt:
        return res
    try:
        from truthstone.intent import premise_names

        have = {a.name for a in res.missing}
        skip = set(already or ()) | have
        for a, only, _kind in premise_names.relied(P, prompt, root, files, already=skip):
            if a.name in have:
                continue
            have.add(a.name)
            res.missing.append(a)
            if only:
                res.only_in[a.name] = only
        res.recorded = [a for a in res.recorded if a.name not in have]
    except Exception:  # fail open: the names already found stand
        import logging

        logging.getLogger(__name__).info("truthstone: the relied-switch check could not run", exc_info=True)
    return res
