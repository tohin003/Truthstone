"""Day 6 (C7): the switches a request relies on, judged by the name and the repository, not by the wording.

Every new false-premise task words its claim differently ("<x> honours `N`", "<x> takes ... from `N`",
"`N=off` turns ...", "<x> has a kill switch"); a check that waits for an existence wording misses about
half of them. The way a request USES a configuration switch is far less varied than the way it CLAIMS
one: it gives the switch a value (`N=1`, `n = true`, `"n": 200`), asks to set, enable, pass or raise it,
or names it as where present behaviour comes from ("from `N`", "when `N`", "with `--n`"). This rule
starts from the names:

* **Switch-like names** in the request: environment-style names (`ALL_CAPS_WITH_PARTS`), `--flags`,
  keys given a value in a code span (`n = 1`, `n: true`, `"n": 2`), keyword arguments in a call span,
  back-quoted compound identifiers (`snake_case`, `camelCase`, `kebab-case`), and a bare compound
  identifier the request calls an option, setting, flag or key.
* **Relied on, unless created.** A name the request gives a value, uses, or names as the source or the
  condition of present behaviour is relied on; it is excused only when the request asks for it to be
  made (add, introduce, implement, support, new, "should ...", rename to, called/named, configurable),
  says it is absent or removed, or builds its read ("read the timeout from `N`").
* **Not another program's.** Tool and runtime switches (fixed lists, a tool named in the sentence or
  a tool's command line, tool-owned configuration), a library's options (a call the project does not
  define, a library named with it, "forwards its keyword arguments to ..."), an external service's
  parameters, credentials and endpoints. A well-known convention variable (colour, pager, editor) is
  the project's only when the request says the project's own program honours it and nothing the
  project runs could read it (no runtime dependency, no colour-aware runtime call).
* **Nothing reads it.** The name (and its spelling variants) occurs in no code or test file and no
  tool's configuration; at most in docs, history, CI, compose or environment templates. An env name
  read through a computed prefix (`PREFIX_${key}`) is read only when the suffix names something the
  repository has.

What it finds joins the prompt-time premise note (and so the first-edit hold and the Stop check).
Precision first: unknown or unreadable means silent; at most a few names per prompt.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path, PurePosixPath

# -- candidates --------------------------------------------------------------------------------------

_ENV = re.compile(r"(?<![\w$.-])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![\w-])")
_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![\w-])")
_TICK = re.compile(r"`([^`\n]{1,160})`")
_COMPOUND = re.compile(r"^(?:[a-z][a-z0-9]*(?:[_-][a-z0-9]+)+|[a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)+)$")
_BARE_COMPOUND = re.compile(
    r"(?<![\w./@`'\"-])([a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)+)(?![\w/@`'\"(-])"
)
_SPAN_KEY = re.compile(r"^\s*[\"']?([A-Za-z_][\w-]*)[\"']?\s*(=|:)\s*(?!=)(\S.*)$")
_CALL_SPAN = re.compile(r"^@?([A-Za-z_][\w.]*)\((.*)\)$")
_DOTTED_SPAN = re.compile(r"^([a-z][\w-]*)\.([A-Za-z_][\w-]*)$")
_SWITCH_NOUN_AFTER = re.compile(
    r"^[`'\"]?\s*(?:(?:[a-z]+[\s-]+){0,2})?(?:option|setting|flag|key|field|parameter|param|kwarg|argument|variable"
    r"|switch|toggle|mode|property|constant|env\s+var)s?\b",
    re.I,
)
_SET_VERB_BEFORE = re.compile(
    r"\b(?:set|sets|setting|enable|enables|disable|turn\s+on|switch\s+on|flip\s+on|raise|lower|increase|decrease"
    r"|bump|reduce|change|pass|passes|passing|use|using)\s+(?:the\s+|its\s+|[\w`'.()]+'s\s+)?[`'\"]?$",
    re.I,
)
_HEADER_CASE = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z0-9]*)+$")
_VALUE_WORD = re.compile(r"^(?:true|false|none|null|yes|no|on|off|nan|inf)$", re.I)
_FILE_LIKE = re.compile(r"\.(?:[a-z]{1,5})$")

# -- stance -------------------------------------------------------------------------------------------

_APOS = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})
_CLAUSE = re.compile(r"[;:](?=\s)|\s[\u2014\u2013-]{1,2}\s|\.\s")
# Creation, governing the name: a creating verb in the name's clause before it, no possession in between.
_CREATE_BEFORE = re.compile(
    r"\b(?:add|adding|added|introduce|introducing|introduced|create|creating|created|implement|implementing"
    r"|implemented|define|defining|declare|declaring|support|supporting|expose|exposing|teach|teaching|wire|wiring"
    r"|give|giving|allow|allowing|accept|accepting|new|rename\w*|called|named|become|becomes|make|making|let|store|storing"
    r"|record|recording|track|tracking|keep\s+track|generate|generating|extract|extracting|move|moving|replace"
    r"|replacing|switch\s+to|convert|converting|emit|emitting|return|returning|output|outputting|print|printing"
    r"|log|logging|raise\s+an?|throw|throwing|optional|configurable|instead)\b"
    r"(?![^.;:!?]{0,80}?\b(?:has|have|had|takes|reads|honou?rs|supports|accepts|already|existing|currently)\b)"
    r"[^.;:!?]{0,80}$",
    re.I,
)
# A modal in the name's clause: the request describes behaviour to build, not behaviour that is there.
_MODAL = re.compile(
    r"\b(?:should(?!\s+already)|must|needs?\s+to|has\s+to|have\s+to|ought\s+to|will(?!\s+you\b)|would(?!\s+you\b)|shall|want|wants"
    r"|wanted|need|needs|'d\s+like|would\s+like|like\s+(?:it|to)|going\s+to|plan\s+to|intend\s+to|could\s+(?!you\b))\b",
    re.I,
)
# Absence or removal tied to the request's view of the name.
_ABSENT_NEAR = re.compile(  # in the five words before the name
    r"\b(?:no|not|never|without|lacks?|lacking|missing|absent|doesn|don|isn|aren|wasn|hasn|haven|nothing|none"
    r"|remove|removes|removed|removing|delete|deletes|deleted|drop|drops|dropped|rip|retire|retired|deprecated"
    r"|legacy|dead|stale|obsolete|former|previous|unused|ignores|ignored|replace|replaces|replaced)\b",
    re.I,
)
_ABSENT_AFTER = re.compile(  # right after the name
    r"^[`'\"]?\s*(?:\([^)]{0,60}\)\s*)?(?:(?:flag|option|setting|key|variable|switch|kwarg|argument|parameter|field"
    r"|env\s+var)s?\s+)?(?:(?:doesn'?t|does\s+not|isn'?t|is\s+not|don'?t|aren'?t|are\s+not|was\s+never|never|no\s+longer)"
    r"\s+(?:yet\s+|currently\s+|actually\s+)?(?:exists?|there|supported|implemented|available|wired|defined|read|used"
    r"|known|work|works|do|does|affect|change)|(?:is|are|was|were)\s+(?:missing|gone|removed|deleted|dropped|deprecated"
    r"|unused|dead|new|not\s+yet)|(?:has|have)\s+been\s+(?:removed|deleted|dropped)|instead\s+of|rather\s+than"
    r"|\(?(?:removed|deleted|dropped|deprecated|gone)\b)",
    re.I,
)
_NOT_REAL = re.compile(  # an example of a wrong value, not a switch: "a mistyped `--ten`", "an unknown `x`"
    r"\b(?:mistyped|misspelt|misspelled|typo(?:ed)?|wrong|bogus|invalid|unknown|unrecognised|unrecognized|bad"
    r"|shortened|abbreviated|truncated|fake|made-up|nonexistent|non-existent|e\.g|eg|example|such\s+as)\b",
    re.I,
)
_WORDS = re.compile(r"[A-Za-z][\w'.-]*")
_MODAL_AFTER = re.compile(
    r"^[`'\"]?\s*(?:\([^)]{0,60}\)\s*)?(?:should(?!\s+already)|must|needs?\s+to|has\s+to|will|would|shall)\b",
    re.I,
)
# Audit (day 6): a switch given a value, then a modal, is behaviour to build as much as "`n` should default
# to 3" is: "N=1 should turn every flag off", "N=1 scripts/x.sh should skip the copy" (the value, at most one
# script path, then should/must/needs to/has to; never "should already").
_VALUED_MODAL_AFTER = re.compile(
    r"^[`'\"]?\s*=\s*[^\s`'\"]+[`'\"]?\s+(?:[\w.$-]*/[\w./$-]*\s+)?(?:should(?!\s+already)|must|needs?\s+to|has\s+to)\b",
    re.I,
)
_CREATING_OPENER = re.compile(
    r"^\W*(?:[A-Z][\w ]{0,20}:\s+)?"
    r"(?:(?:please|pls|kindly|so|and|then|now|also|just|first|finally|hi|hey|thanks|ok)\W+)*"
    r"(?:(?:can|could|would|will)\s+(?:you|we)\s+(?:please\s+)?|(?:i|we)\s+(?:need|want|would\s+like|'d\s+like)\s+(?:you\s+)?"
    r"(?:to\s+)?|let'?s\s+|it'?d\s+be\s+(?:great|nice)\s+(?:if\s+(?:you|we)\s+(?:could\s+)?)?(?:to\s+)?)?"
    r"(?:add|implement|create|introduce|build|write|define|declare|support|expose|teach|give|make|let|allow|extend"
    r"|store|record|track|rename|move|extract|replace|refactor|convert|switch|change|update|fix|handle|validate"
    r"|generate|emit|return|log|print|show|display|document|describe|explain|remove|delete|drop|split|merge"
    r"|wrap|parse|read|load|default|redact|mask|cache|retry|sort|group|filter|count|sum|compute|calculate|format"
    r"|round|cap|limit|reject|raise|throw|accept|allow|keep|stop|start|send|post|fetch|decode|encode|declare)\b"
    r"(?![-./])",
    re.I,
)
_READ_BUILD = re.compile(  # "read the timeout from `N`" at the head of a clause: builds the read
    r"(?:^|[.;:!?,]\s*|\b(?:please|then|also|and|so|to|should|must|can\s+you|could\s+you)\s+)"
    r"(?:read|take|load|pull|get|default|fall\s+back|source|configure|derive|pick\s+up)\b[^.;:!?]{0,80}$",
    re.I,
)
_RENAME_TO = re.compile(
    r"\b(?:rename\w*|renaming)\b[^.;!?]{0,80}?\b(?:to|into|as)\s+[`'\"]?$|->\s*[`'\"]?$|→\s*[`'\"]?$", re.I
)
_NEXT_CREATES = re.compile(
    r"^\W*(?:(?:so|then|please|just|and)\s+)*(?:add|introduce|create|implement|define|declare|build|wire)\s+"
    r"(?:it|one|that|this|them)\b|^\W*(?:it|that|this|the\s+\w+)\s+(?:doesn'?t|does\s+not|isn'?t|is\s+not)\s+"
    r"(?:exist|there|implemented|supported|read|wired)",
    re.I,
)
_WHOLE_SENTENCE_CREATES = re.compile(
    r"\b(?:configurable|support\s+for|make\s+it\s+possible|is\s+new|are\s+new|brand[-\s]new|from\s+scratch)\b",
    re.I,
)

# -- external owners -----------------------------------------------------------------------------------

_TOOLS = re.compile(
    r"\b(?:pytest(?:-cov)?|py\.test|coverage|tox|nox|pipx?|uvx?|poetry|pdm|hatch|ruff|black|isort|flake8|pylint|mypy"
    r"|pyright|npm|npx|yarn|pnpm|tsc|tsx|ts-node|typescript|jest|vitest|mocha|playwright|cypress|eslint|prettier"
    r"|webpack|vite|esbuild|rollup|babel|git|github|gh|gitlab|docker(?:-compose)?|podman|compose|kubectl|kubernetes"
    r"|k8s|helm|terraform|ansible|cargo|rustc|mvn|gradle|dotnet|curl|wget|rsync|gunicorn|uvicorn|celery|nginx|caddy"
    r"|apache|systemd|cron|bash|zsh|python3?|node|nodejs|deno|bun|java|jvm|ssh|openssl|sqlite3?|postgres(?:ql)?"
    r"|psql|mysql|redis|actions|travis|circleci|jenkins|buildkite|vercel|netlify|heroku|aws|gcloud|azure|sentry"
    r"|mkdocs|sphinx|jekyll|hugo|uv|pre-commit|renovate|dependabot|codecov|editorconfig|browserslist|chrome|firefox"
    r"|excel|sheets|grafana|prometheus|datadog|kafka|rabbitmq|elasticsearch|stripe|twilio|sendgrid|slack|s3)\b",
    re.I,
)
_TOOL_NOUN = re.compile(
    r"\b(?:test\s+runner|linter|formatter|type\s*checker|compiler|bundler|transpiler|interpreter|runtime"
    r"|package\s+manager|ci\s+runner|shell|browser|editor|terminal|os|operating\s+system|kernel|database"
    r"|load\s+balancer|proxy|reverse\s+proxy|web\s+server|container|image|registry|cluster|orchestrator"
    r"|matrix|workflow\s+syntax|action|github\s+action)s?\b",
    re.I,
)
_ARG_NOUN = (
    r"(?:(?:its|their|the|any|all|every|extra|other|remaining|unknown|additional|keyword|command[-\s]line)\s+)*"
    r"(?:arguments|args|argv|kwargs|keyword\s+arguments|options|opts|flags|params|parameters|settings|props"
    r"|everything|anything|the\s+rest)"
)
_FORWARDS = re.compile(
    rf"\b(?:forwards?|forwarded|forwarding|passes|passed|hands?|handed|relays?|proxies|spreads?|splats?|delegates?"
    rf"|pipes?)\s+(?:\S+\s+){{0,2}}?{_ARG_NOUN}\b"
    r"|\b(?:passes|passed|hands|handed)\s+(?:\S+\s+){0,3}?(?:straight\s+)?(?:through|along|on)\s+to\b"
    r"|\bthrough\s+to\s+`?[\w.-]+|\"\$@\"|\$@|\*\*kwargs|\.\.\.\s*(?:options|opts|args|rest|props)\b"
    r"|\banything\s+after\s+--",
    re.I,
)
_LIB_SAID = re.compile(
    r"\b(?:we|i)\s+(?:use|used|rely\s+on|depend\s+on|added|adopted|call|parse\s+\S+\s+with|render\s+\S+\s+with)\b"
    r"|\b(?:library|package|module|sdk|framework|dependency|plugin|client\s+library|standard\s+library|stdlib"
    r"|built-?in)\b",
    re.I,
)
_OWN_SERVICE = re.compile(r"\b(?:our|my|the\s+project'?s)\s+(?:[\w-]+\s+){0,2}(?:api|service|server)\b", re.I)
_SECRET = re.compile(
    r"(?:API_?KEY|_KEY|_TOKEN|_SECRET|_PASSWORD|_PASSWD|_DSN|_URL|_URI|_HOST|_PORT|_ENDPOINT|_REGION|_BUCKET|_USER"
    r"|_DB|_DATABASE|_PATH|_DIR|_FILE)$"
)
# Conventions a program implements itself (no runtime reads them for the program's own output), and the
# runtime or library calls that do read them when a program uses those.
_CONVENTIONS = frozenset(
    {"FORCE_COLOR", "NO_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "PAGER", "EDITOR", "VISUAL"}
)
_CONVENTION_READERS = re.compile(
    r"\b(?:hasColors|getColorDepth|styleText|supportsColor|supports-color|supports_color|chalk|kleur|colorette"
    r"|picocolors|ansi-colors|colorama|termcolor|rich|click\.style|click\.echo|isatty_color|colorize|can_colorize"
    r"|_can_colorize|inspect\s*\([^)]*colors|pydoc|less|more|editor|launch_editor|click\.edit|click\.echo_via_pager)\b"
)
_PRESENT_READ = re.compile(
    r"^\s*(?:already\s+|also\s+)?(?:honou?rs|respects|reads|supports|understands|recogni[sz]es|obeys|picks\s+up|takes"
    r"|accepts|uses|follows|checks|looks\s+(?:at|for))\b",
    re.I,
)

_CODE_SPANS = re.compile(r"`[^`\n]*`")
_DQUOTED = re.compile(r"\"[^\"\n]{1,200}\"")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Za-z`'\"(])|\n\s*\n")

MAX_NAMES = 6


def _sentences(prompt: str) -> list[tuple[int, str]]:
    out, start = [], 0
    for m in _SENT.finditer(prompt):
        if m.start() > start:
            out.append((start, prompt[start : m.start()]))
        start = m.end()
    if start < len(prompt):
        out.append((start, prompt[start:]))
    return out


def _clause_bounds(s: str, off: int, length: int) -> tuple[int, int]:
    start, end = 0, len(s)
    for m in _CLAUSE.finditer(s):
        if m.end() <= off:
            start = m.end()
        elif m.start() >= off + length:
            end = m.start()
            break
    return start, end


def _in_dquotes(s: str, off: int) -> bool:
    """Inside a double-quoted phrase of the prose (an output, a label, a message), not inside a code span."""
    blank = _CODE_SPANS.sub(lambda m: "x" * len(m.group(0)), s)
    return any(m.start() < off < m.end() for m in _DQUOTED.finditer(blank))


def candidates(s: str) -> list[tuple[int, str, str, str, bool]]:
    """(offset, name, kind, callee, valued) for the switch-like names of one sentence. ``kind``: env, flag,
    key, kw, name, dotted. ``valued``: the request gives it a value right there."""
    found: dict[str, tuple[int, str, str, str, bool]] = {}

    def put(off: int, name: str, kind: str, callee: str = "", valued: bool = False) -> None:
        if not name or name in found:
            if name in found and valued and not found[name][4]:
                o, n, k, c, _v = found[name]
                found[name] = (o, n, k, c or callee, True)
            return
        found[name] = (off, name, kind, callee, valued)

    for m in _TICK.finditer(s):
        inner = m.group(1)
        base = m.start(1)
        strip = inner.strip()
        lead = len(inner) - len(inner.lstrip())
        call = _CALL_SPAN.match(strip)
        if call:
            args = call.group(2)
            a0 = base + lead + call.start(2)
            for kw in re.finditer(r"(?<![\w.\-\"'])([a-z_][A-Za-z0-9_]{2,})\s*=(?!=)", args):
                put(a0 + kw.start(1), kw.group(1), "kw", call.group(1), True)
            for kw in re.finditer(r"(?<![\w.\-\"'])([a-z_][A-Za-z0-9_]{2,})\s*:\s*(?!:)", args):
                if "{" in args:
                    put(a0 + kw.start(1), kw.group(1), "kw", call.group(1), True)
            continue
        if strip.startswith("{") and strip.endswith("}"):
            body = strip[1:-1]
            keys = list(re.finditer(r"[\"']?([A-Za-z_][\w-]*)[\"']?\s*:", body))
            if len(keys) == 1:  # `{ "n": 1 }`; several keys are a value's shape, not a switch
                k = keys[0]
                put(base + lead + 1 + k.start(1), k.group(1), "key", "", True)
            continue
        for env in _ENV.finditer(inner):
            put(base + env.start(1), env.group(1), "env", "", inner[env.end(1) : env.end(1) + 1] == "=")
        kwonly = re.fullmatch(r"([a-z_][A-Za-z0-9_]{2,})=", strip)
        if kwonly:
            put(base + lead, kwonly.group(1), "kw", "", True)
            continue
        kv = _SPAN_KEY.match(strip)
        if (
            kv
            and kv.group(2) == ":"
            and not re.match(r"\s|[\"'\d\[{-]|true|false|null|none|on\b|off\b", strip[kv.end(2) :], re.I)
        ):
            continue  # `build:prod`, `test:ci`: a script name, not a key
        if kv and " " not in kv.group(1):
            key = kv.group(1)
            rest = kv.group(3)
            if _ENV.fullmatch(key):
                put(base + lead + kv.start(1), key, "env", "", True)
            elif not rest.startswith(("//", "/")) and len(key) >= 3:
                put(base + lead + kv.start(1), key, "key", "", True)
            continue
        if strip.startswith("--"):
            flag = _FLAG.match(strip)
            if flag:
                rest = strip[flag.end(1) :]
                put(base + lead, flag.group(1), "flag", "", bool(rest.strip()) and not _metavar(rest))
            continue
        dotted = _DOTTED_SPAN.match(strip)
        if dotted:
            put(base + lead, strip, "dotted")
            continue
        if _COMPOUND.match(strip) and len(strip) >= 4:
            put(base + lead, strip, "name")
            continue
        if _ENV.fullmatch(strip):
            put(base + lead, strip, "env")
    blank = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), s)
    for m in _ENV.finditer(blank):
        name = m.group(1)
        valued = blank[m.end(1) : m.end(1) + 1] == "="
        put(m.start(1), name, "env", "", valued)
    for m in _FLAG.finditer(blank):
        rest = blank[m.end(1) : m.end(1) + 40]
        put(m.start(1), m.group(1), "flag", "", bool(re.match(r"[ =][^\s-]", rest)) and not _metavar(rest))
    for m in _BARE_COMPOUND.finditer(blank):
        name = m.group(1)
        if len(name) < 4:
            continue
        after = s[m.end(1) :]
        before = s[: m.start(1)]
        if (
            _SWITCH_NOUN_AFTER.match(after)
            or _SET_VERB_BEFORE.search(before[-40:])
            or re.match(r"\s*(?:=|:)\s*(?!=)\S", after)
        ):
            put(m.start(1), name, "name", "", bool(re.match(r"\s*(?:=|:)\s*(?!=)\S", after)))
    return sorted(found.values())


# Audit (day 6): usage notation after a flag is its argument's name, not a value given to it: "--below N",
# "--db PATH", "--max-length <n>", "--since {date}" describe the flag ("show --below N: only SKUs under N"),
# where "--batch-size 500" or "--country DE" set it.
_METAVAR = re.compile(
    r"^[ =](?:[A-Z]|N|NUM|COUNT|PATH|FILE|DIR|NAME|KEY|VALUE|ID|COLUMN|DATE|URL|SECONDS|MS|QTY|SIZE|LIMIT"
    r"|LEVEL|MODE|<[^<>\s]{1,20}>|\{[^{}\s]{1,20}\}|\[[^\[\]\s]{1,20}\])(?![\w<>{}\[\]=-])"
)


def _metavar(rest: str) -> bool:
    return bool(_METAVAR.match(rest) or _NOT_A_VALUE.match(rest))


# Day 7 (a blind honest set): the word after a flag in prose is its value only when it can be one.
# "can it take --open-only so we just see ..." gives the flag no value; "--country DE", "--limit 50" do.
_NOT_A_VALUE = re.compile(
    r"^ (?:so|and|or|but|nor|to|for|that|which|who|when|whenever|if|unless|in|on|at|of|by|with|without"
    r"|then|than|the|a|an|is|are|was|were|be|as|from|into|onto|because|since|while|until|instead|too|also"
    r"|it|its|this|these|those|they|them|we|you|i|option|flag|switch|argument|parameter|should|would"
    r"|could|can|will|must|might|may|please|here|there|now|still|just|only|even|etc)\b",
    re.I,
)


_UNIVERSAL_FLAGS = frozenset({"--help", "--version", "--verbose", "--quiet", "--debug"})


def _skip_name(name: str, kind: str) -> bool:
    bare = name.lstrip("-")
    return bool(
        name in _UNIVERSAL_FLAGS
        or _HEADER_CASE.match(name)
        or _VALUE_WORD.match(bare)
        or bare.lower().startswith(("test_", "test-"))
        or bare.lower().endswith(("_test", "_spec"))
        or (kind not in ("env", "flag", "dotted") and _FILE_LIKE.search(bare) and "." in bare)
        or "://" in name
        or len(bare) < (2 if kind == "flag" else 3)
    )


# -- stance -------------------------------------------------------------------------------------------


def _created_here(s: str, off: int, name: str, nxt: str) -> bool:
    """The request makes the name (or says it is absent, gone or not real), in the name's own clause, in the
    few words around it, or in the next sentence."""
    cstart, _cend = _clause_bounds(s, off, len(name))
    blank = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), s)
    before = blank[cstart:off].rstrip("`'\" ")
    after = s[off + len(name) : off + len(name) + 80]
    near_before = " ".join(_WORDS.findall(blank[max(cstart, off - 60) : off])[-5:])
    if _CREATE_BEFORE.search(before + " ") and not _puts_into_place(s, off, name):
        return True  # "add `"k": 2` to data/x.json", "add `--x` to the deploy call" put a switch into a place
    if _RENAME_TO.search(blank[max(0, off - 120) : off]):
        return True
    if _MODAL.search(before[-70:]) or _MODAL_AFTER.match(after) or _VALUED_MODAL_AFTER.match(after):
        return True  # "it should honour `n`", "`n` should default to 3", "N=1 should ...": behaviour to build
    from truthstone.intent import premise as _premise

    if _premise.conditional_spec(s, off, name):
        return True  # "if `N` is set, load ... from there": the condition of an instruction (audit, day 6)
    if _ABSENT_NEAR.search(near_before) or _ABSENT_AFTER.match(after) or _NOT_REAL.search(near_before):
        return True
    if _READ_BUILD.search(before + " "):
        return True
    if _WHOLE_SENTENCE_CREATES.search(blank):
        return True
    if re.match(r"^[`'\"]?\s*\(\s*(?:a\s+)?new\b|^[`'\"]?\s*\(\s*optional\b", after, re.I):
        return True
    if nxt and (_NEXT_CREATES.search(nxt) or _NEXT_NEW.search(nxt)):
        return True
    tail = _FILE_TOKEN.sub(lambda m: "x" * len(m.group(0)), blank[off + len(name) : off + len(name) + 160])
    if _WIRE_AFTER.match(tail) or _BUILD_IT.search(s) or (nxt and _BUILD_IT.search(nxt)):
        return (
            True  # "set `N=1` in x.env and read it in `f`", "...; implement it": the request builds the read
        )
    return _SAYS_NEW(s) or _SAYS_NEW(nxt)


_WIRE_AFTER = re.compile(
    r"^[^.;!?]{0,120}?\b(?:and|then|,)\s+(?:also\s+)?(?:make\s+\S+\s+)?(?:read|reads|load|loads|parse|parses|honou?r"
    r"|honou?rs|wire|plumb|thread|hook\s+up|pick\s+up|respect|enforce|enforces|check|implement|handle)"
    r"\s+(?:it|them|that|this|the\s+(?:value|setting|flag|option|variable|key|cap|limit))\b",
    re.I,
)
_BUILD_IT = re.compile(
    r"\b(?:implement|build|wire\s+up|hook\s+up|support|code\s+up)\s+(?:it|this|that|them|the\s+(?:behaviou?r|feature|logic"
    r"|reader|read|check|support))\b|\bmake\s+(?:it|that|this)\s+(?:work|happen|real)\b",
    re.I,
)


# The dead-switch rule's "not read yet" forms (``dead_switch._SAYS_NEW``), less "switch ... over to".
_NOT_READ_YET = re.compile(
    r"\bnothing\s+(?:\w+\s+){0,3}?reads\b|\b(?:isn'?t|is\s+not|aren'?t|are\s+not)\s+(?:read|used|wired)\s+"
    r"(?:anywhere|yet|by\s+anything)|\bno\s+code\s+(?:\w+\s+){0,2}?reads\b"
    r"|\b(?:wire|hook|plumb)\s+(?:it|that|this|them)\s+(?:up|in|through)\b"
    r"|\buse\s+the\s+(?:new\s+)?(?:config|configured|setting)\s+value\b"
    r"|\b(?:needs?|has|have|should|must|will\s+need)\s+to\s+(?:start\s+)?(?:read|reading|use|using|honou?r|pick\s+up)\b"
    r"|\bstart\s+(?:reading|using|honou?ring)\b",
    re.I,
)


def _SAYS_NEW(text: str) -> bool:
    from truthstone.intent import dead_switch as D

    return bool(text) and (bool(_NOT_READ_YET.search(text)) or bool(D._FOLLOW_ABSENT.match(text)))


_NEXT_NEW = re.compile(
    r"^\W*(?:(?:it|this|that|the\s+\w+(?:\s+\w+)?)\s+(?:is|'s|are)\s+(?:a\s+|brand\s+)?new\b|it'?s\s+(?:a\s+)?new\b"
    r"|(?:it|this|that)\s+(?:doesn'?t|does\s+not|isn'?t|is\s+not)\s+(?:exist|read|used|wired|there)"
    r"|nothing\s+(?:\w+\s+){0,3}reads\s+(?:it|that|this)|(?:\w+\s+){0,4}(?:still\s+)?hard-?codes?\b)",
    re.I,
)


_INVOCATION_STRICT = re.compile(
    r"\b(?:call|command|invocation|run|step|job|target|entry|line|script|cron|crontab|dockerfile|makefile|workflow"
    r"|pipeline|procfile|env\s+file|environment|section|table|block)\b",
    re.I,
)
_PLACE_SUFFIX = frozenset(
    {
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".properties",
        ".env",
        ".sh",
        ".bash",
        ".zsh",
        ".service",
        ".mk",
    }
)
_PLACE_NAME = re.compile(
    r"^(?:Dockerfile[\w.-]*|Makefile|makefile|Procfile|crontab|\.env(?:\.[\w-]+)?|[\w.-]+\.env)$"
)
_SOURCE_SUFFIX = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".go", ".rs", ".rb"}
)


def _span_end(s: str, off: int) -> int:
    """The end of the code span holding ``off`` (or ``off`` itself outside a span)."""
    for m in _CODE_SPANS.finditer(s):
        if m.start() <= off < m.end():
            return m.end()
    return off


def _good_place(place: str) -> bool:
    if re.search(
        r"\b(?:parser|argparse|schema|cli\s+definition|options?\s+(?:list|table)|interface|type)\b",
        place,
        re.I,
    ):
        return False
    path = re.search(r"`([^`\n]+)`|([\w./-]+\.[A-Za-z]\w*)", place)
    if path:
        p = (path.group(1) or path.group(2)).split()[0]
        suffix = PurePosixPath(p).suffix.lower()
        if suffix in _SOURCE_SUFFIX:
            return bool(_INVOCATION_STRICT.search(place[path.end() :]))
        if suffix in _PLACE_SUFFIX or _PLACE_NAME.match(PurePosixPath(p).name):
            return True
    return bool(_INVOCATION_STRICT.search(place))


_TO_PLACE = re.compile(
    r"\b(?:to|in|into|on|at)\s+(?P<place>(?:the\s+|our\s+|its\s+)?(?:`[^`\n]+`|[\w./:'-]+)(?:\s+[\w:'.-]+){0,4})",
    re.I,
)


def _puts_into_place(s: str, off: int, name: str) -> bool:
    """ "add `n = 1` to x.toml", "add `--x` to the `y` call", "add `N=1` to deploy/z.env": a switch given a
    value
    (or a flag) goes into a place where switches are set, not a parser or a source file to build it in. "add a
    `n` key to x.json" makes a new key: not a put."""
    blank = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), s)
    head = blank[max(0, off - 60) : off]
    if re.search(r"\b(?:a|an|another|new|one|the\s+new)\s*[`'\"]?\s*$", head, re.I):
        return False
    start = _span_end(s, off)
    tail = s[start : start + 160]
    flat = _FILE_TOKEN.sub(
        lambda m: "x" * len(m.group(0)), _CODE_SPANS.sub(lambda m: "x" * len(m.group(0)), tail)
    )
    for m in _TO_PLACE.finditer(tail):
        if re.search(r"[.;!?](?=\s|$)", flat[: m.start()]):
            break
        if _good_place(m.group("place")):
            return True
    return False


_USE_OPENER = re.compile(
    r"^\W*(?:(?:please|pls|so|and|then|now|also|just|first|finally)\W+)*(?:(?:can|could|would|will)\s+you\s+"
    r"(?:please\s+)?)?(?:set|enable|use|pass|turn|switch|flip|raise|lower|increase|decrease|bump|reduce|put|prefix"
    r"|export|apply|include|construct|call|run|invoke|configure)\b",
    re.I,
)
_CONTINUES = re.compile(r"^\W*(?:(?:then|and|also|plus)\s+)?(?:a|an|another)\s", re.I)


def _creating_sentence(sents: list[str], i: int, off: int, name: str) -> bool:
    """A sentence, or the clause of it holding the name, that opens by asking for something to be built or
    changed: its names are the change's own, unless the clause opens with a use ("...: set `N=1` in x") or the
    switch is put into a configuration place or an invocation ("Add `--x` to the deploy call"). A sentence
    that only continues a build request ("then a `x --n N` command ...") is part of it."""
    s = sents[i]
    cstart, _ = _clause_bounds(s, off, len(name))
    clause = s[cstart:]
    if _USE_OPENER.match(clause):
        return False
    opener = _CREATING_OPENER.match(clause) or (cstart and None) or _CREATING_OPENER.match(s)
    if opener is None and i and _CONTINUES.match(s) and any(_CREATING_OPENER.match(x) for x in sents[:i]):
        opener = True
    if not opener:
        return False
    if opener is not True:
        head = opener.group(0).strip().lower().split()[-1]
        if head in ("set", "enable", "use", "pass", "turn", "raise", "lower"):
            return False
    return not _puts_into_place(s, off, name)


_OBJECT_OPENER = re.compile(
    r"\b(?:add|implement|create|introduce|build|support|expose|give|teach|track|record|store|make)\s+"
    r"(?P<obj>(?:(?:a|an|the|some|new|optional|user|per-\w+)\s+)*(?:[a-z][\w-]*\s+){0,3}?[a-z][\w-]*)",
    re.I,
)


def _stem(word: str) -> str:
    w = re.sub(r"[^a-z]", "", word.lower())
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "s", "y", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: len(w) - len(suf)]
    return w


def creation_objects(sents: list[str]) -> set[str]:
    """Stems of the words a request asks to be built ("Please add user segments to x": segment, user)."""
    out: set[str] = set()
    for s in sents:
        if not _CREATING_OPENER.match(s):
            continue
        for m in _OBJECT_OPENER.finditer(s[:200]):
            for w in m.group("obj").split():
                st = _stem(w)
                if len(st) >= 4 and w.lower() not in ("optional", "new", "user", "some", "the"):
                    out.add(st)
    return out


def _made_by_object(name: str, objects: set[str]) -> bool:
    parts = [p for p in re.split(r"[_\-.]|(?<=[a-z])(?=[A-Z])", name.lstrip("-")) if p]
    return bool(parts) and any(_stem(p) in objects for p in parts if len(p) >= 4)


_CLAIM_VERB = re.compile(
    r"\b(?:supports|has|have|takes|accepts|honou?rs|reads|respects|understands|exposes|provides|offers|recogni[sz]es"
    r"|uses|checks|looks\s+(?:at|for)|picks\s+up|pulls|loads|skips|switches|turns|logs|prints|caps|trims|appends"
    r"|drops|keeps|sizes|comes\s+from|defaults\s+to|when|whenever|if|once)\b",
    re.I,
)
_SET_TO_VALUE = re.compile(
    r"\b(?:set|raise|lower|change|bump|increase|decrease|reduce|cap|limit)\s+(?:the\s+|its\s+)?[`'\"]?$", re.I
)


def _env_relied(sents: list[str], i: int, off: int, name: str, valued: bool) -> bool:
    """An env name is relied on when the request assigns it (`N=1`, "set `N` to 2") or says what it does
    ("<x> reads `N`", "when `N` is set", "the pool size comes from `N`"); otherwise "use the `N` env var for
    the timeout" introduces it."""
    s = sents[i]
    prev = sents[i - 1] if i else ""
    if valued:
        return True
    before = s[max(0, off - 60) : off]
    after = s[off + len(name) : off + len(name) + 80]
    if _SET_TO_VALUE.search(before) and re.match(
        r"^[`'\"]?\s*(?:\([^)]{0,80}\)\s*)?(?:to|=)\s+\S", after, re.I
    ):
        return True
    if _THERE_IS_A.search(before):
        return True  # day 7: "there's a `N` setting in x": the existence claim governs the name itself
    return bool(_CLAIM_VERB.search(_CODE_SPANS.sub(" ", s)) or _CLAIM_VERB.search(prev))


# "there's a `N` ...", "there is already an `N` ...": an existence claim whose object is the name (as "x has
# a `N` setting" is through ``_CLAIM_VERB``); never "there's no", "there should be", "there's a new".
_THERE_IS_A = re.compile(
    r"\b(?:there'?s|there\s+is|there\s+are)\s+(?:already\s+|also\s+)?(?:a|an|the)\s+[`'\"]?$", re.I
)


_NEW_LABEL = re.compile(
    r"^\W*(?:new|proposal|feature(?:\s+request)?|todo|to\s+do|idea|plan)\s*[:\-\u2014]", re.I
)
_USE_VERBS = re.compile(
    r"\b(?:set|enable|disable|turn|switch|flip|pass|use|add|put|raise|lower|increase|decrease|bump|reduce|change"
    r"|include|apply|export|prefix|configure|construct|call|run|append|insert|extend|shorten|lengthen)\b",
    re.I,
)


def _used(sents: list[str], i: int, off: int, name: str, valued: bool) -> bool:
    """The request asks for something to be done with the name: it gives it a value, or the sentence (or the
    next one) asks to set, enable, pass, add, raise ... A bare statement ("x reads `n` from y.") asks nothing.
    """
    nxt = sents[i + 1] if i + 1 < len(sents) else ""
    if valued:
        return not _value_described(sents[i], off, name, nxt)
    s = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), sents[i])
    if _USE_VERBS.search(s):
        return True
    return bool(nxt and _USE_OPENER.match(nxt))


# Day 7 (a blind honest set): "N=v makes `f()` round half to even (unset: as now)" only says what the
# value does; with nothing asked to be done with the switch (no set, pass, use, add, enable ... in the
# sentence or the next one) it describes behaviour, as "N=v should ..." does. A value that is also set,
# passed or put somewhere ("N=v skips the copy; set it in x.env") is still a use.
_VALUE_THEN_VERB = re.compile(
    r"^[`'\"]?\s*=\s*[^\s`'\"]+[`'\"]?\s+(?:(?:also|just|then|now|always|only)\s+)?"
    r"(?!(?:is|was|has|does|its|this|thus|as|us|yes|plus|unless|always)\b)[a-z]{2,}s\b",
    re.I,
)


def _value_described(s: str, off: int, name: str, nxt: str) -> bool:
    end = off + len(name)
    m = _VALUE_THEN_VERB.match(s[end : end + 120])
    if not m:
        return False
    blank = _CODE_SPANS.sub(lambda c: " " * len(c.group(0)), s)
    rest = blank[:off] + " " + blank[end + m.end() :]
    return not _USE_VERBS.search(rest) and not (nxt and _USE_VERBS.search(nxt))


def relied_stance(sents: list[str], i: int, off: int, name: str, valued: bool) -> bool:
    """Whether the request relies on ``name`` (at ``off`` in sentence ``i``): not made by the request."""
    s = sents[i]
    nxt = sents[i + 1] if i + 1 < len(sents) else ""
    if _NEW_LABEL.match(s) or (i and _NEW_LABEL.match(sents[i - 1])):
        return False
    if _created_here(s, off, name, nxt):
        return False
    return not _creating_sentence(sents, i, off, name)


# -- external owners -----------------------------------------------------------------------------------


def _owner(PS, s: str, off: int, name: str, kind: str, callee: str, ctx) -> str:
    """The project-defined callable or class the request hands the option to ("pass `n=1` to `f()`", "`f()`'s
    `n` option", "construct the `X` with `n=1`", a keyword inside `f(n=1)`), "" for none; "lib" when the
    callable is not the project's or it forwards its options on."""
    for target in (callee, _call_target(s, off, name)):
        if not target:
            continue
        root = target.split(".", 1)[0].lstrip("@")
        last = target.rpartition(".")[2]
        if root in ("self", "this", "cls"):
            continue
        if "." in target and (
            root in PS._STD_ROOTS
            or not PS._project_owned(PS.Subject("token", token=root, backticked=True), ctx)
        ):
            return "lib"
        defs = ctx.defs(last)
        if not defs:
            return "lib"
        if any(PS._definition_forwards_v51(ctx.text(rel), last, rel) for rel in defs):
            return "lib"
        return target
    return ""


_SUBJECT_VERB = re.compile(
    r"^\s*(?:[a-z][\w-]*\s+){0,2}?(?:already\s+|also\s+|now\s+|currently\s+|still\s+)?(?:reads|takes|honou?rs|uses|has|supports|accepts|skips"
    r"|caps|logs|prints|loads|pulls|picks\s+up|respects|understands|recogni[sz]es|checks|looks\s+(?:at|for)|keeps|drops"
    r"|appends|trims|switches|turns|sizes|applies|expects|wants|requires|needs|knows|gets|defaults|falls\s+back)\b",
    re.I,
)


def _other_subject(PS, s: str, off: int, name: str, ctx) -> bool:
    """A statement whose subject is a program other than the project: "The mail relay reads `n` from x.toml",
    "the load balancer takes `--n`". The subject of the name's clause (or of the sentence) is followed by a
    present-tense claim verb and is neither the project, nor a part of it, nor "our ..."."""
    cstart, _ = _clause_bounds(s, off, len(name))
    for lead in dict.fromkeys((s[cstart:off], s[:off])):
        if not lead.strip():
            continue
        subj = PS._subject(lead)
        if subj.kind in ("", "pronoun", "own"):
            continue
        if not _SUBJECT_VERB.match(lead[subj.end :]):
            continue
        if (
            subj.kind == "token"
            and subj.token
            and (_owned_subject(PS, subj, ctx) or subj.token.lower() in ctx.project_names())
        ):
            return False
        return not (subj.kind == "generic" and PS._generic_files(subj, ctx))
    return False


def _owned_subject(PS, subj, ctx) -> bool:
    """A token subject of the project's own. Day 7: a call written as plain text (`tally()` without
    backticks) is as plainly code as a backticked one, so it is judged the same way (a code file named after
    it or a definition in the repository); the shared ``_project_owned`` tests code-likeness after taking the
    parentheses off and so never saw it. One that forwards its options (`...opts`, `**kwargs`) is not judged
    the project's here: the option may be the library's it hands them to."""
    if PS._project_owned(subj, ctx):
        return True
    if subj.kind != "token" or subj.backticked or not re.fullmatch(r"[A-Za-z_]\w*\(\)", subj.token or ""):
        return False
    bare = subj.token[:-2]
    if any(PS._definition_forwards_v51(ctx.text(rel), bare, rel) for rel in ctx.defs(bare)):
        return False
    return PS._project_owned(PS.Subject("token", token=subj.token, backticked=True, end=subj.end), ctx)


def _anchor(P, PS, sents: list[str], i: int, off: int, name: str, kind: str, callee: str, ctx) -> str:
    """What ties the switch to the project (a short reason), or "": its own callable or class, its own program
    (a repository script or command the flag goes to), its own configuration file (one the code reads), its
    own manifest section, its own name (`<PROJECT>_X`), or a sentence whose subject is the project or a part
    of it."""
    s = sents[i]
    prev = sents[i - 1] if i else ""
    owner = _owner(PS, s, off, name, kind, callee, ctx) if kind in ("kw", "key", "name") else ""
    if owner and owner != "lib":
        return "callable"
    if kind == "env" and _project_prefixed(name, ctx):
        return "project-prefix"
    if kind == "dotted" and _own_head(name, ctx):
        return "own-head"
    if kind == "flag" and _flag_owned(s, ctx):
        return "own-program"
    if kind in ("key", "name"):
        place = _named_place(s)
        if place and _own_section_named(s, place, ctx):
            return "own-section"
        if place and _project_config(place, ctx):
            return "own-config"
    if kind == "env" and _owned_token_in(PS, s, name, ctx):
        return "own-token"
    for text in (
        (s, prev)
        if prev
        and re.match(
            r"^\W*(?:it|this|that|they|its|set|use|pass|enable|turn|switch|raise|lower|please|so|can|could)\b",
            s,
            re.I,
        )
        else (s,)
    ):
        cstart, _ = _clause_bounds(text, off if text is s else len(text), len(name) if text is s else 0)
        for lead in {text, text[cstart:]}:
            subj = PS._subject(lead)
            if subj.kind == "own":
                return "own-subject"
            if subj.kind == "token" and subj.token and _owned_subject(PS, subj, ctx):
                return "subject"
            if subj.kind == "generic" and PS._generic_files(subj, ctx):
                return "generic-subject"
    return ""


def _owned_token_in(PS, s: str, name: str, ctx) -> bool:
    """A code token of the project's own (a class, function or script the repository defines, "the <x>" naming
    one of its files, the project's name) anywhere in the sentence: "(FeedPoller's max delay)", "so the mailer
    logs messages", "so `loadFixtures()` skips the photos"."""
    text = s.replace(name, " ")
    for subj in PS._owner_tokens(text, {name}):
        if subj.kind == "own":
            return True
        if (
            subj.kind == "token"
            and subj.token
            and not PS._is_place(subj.token)
            and PS._project_owned(subj, ctx)
        ):
            return True
        if subj.kind == "generic" and PS._generic_files(subj, ctx):
            return True
    words = {w.lower() for w in re.findall(r"[A-Za-z][\w-]*", text)}
    return bool(words & {n.lower() for n in ctx.project_names()})


_PROGRAM_WORDS = re.compile(
    r"\b(?:our|my|the\s+project'?s)\s+(?:[\w-]+\s+){0,2}(?:cli|command|script|tool|binary|app|program|runner|worker|server|service)\b",
    re.I,
)


def _flag_owned(s: str, ctx) -> bool:
    """The flag goes to the project's own program: the sentence names a repository script or one of the
    project's commands, says "our <cli/script/...>", or names a place whose command line runs the project's
    own program (`node scripts/x.ts` in a package.json script)."""
    from truthstone.intent import dead_switch as D

    files = set(ctx.all_files)
    for m in _SCRIPT_REF.finditer(s):
        rel = m.group(1).lstrip("./")
        if rel in files or any(f.endswith("/" + rel) for f in files):
            return True
    ident = D.project_identity(ctx.root, ctx.files)
    words = {
        w.lower()
        for w in re.findall(r"[\w-]+", _CODE_SPANS.sub(lambda m: " " + m.group(0).strip("`") + " ", s))
    }
    if words & (
        {c.lower() for c in ident["commands"]}
        | {n.lower() for n in ctx.project_names()}
        | set(ident["packages"])
    ):
        return True
    if _PROGRAM_WORDS.search(s):
        return True
    for m in _PLACE_FILE.finditer(s):
        rel = m.group(1).lstrip("./")
        if rel not in files:
            hits = [f for f in files if PurePosixPath(f).name == PurePosixPath(rel).name]
            if len(hits) != 1:
                continue
            rel = hits[0]
        text = ctx.text(rel) or ""
        lines = (
            D._package_script_lines(text.splitlines()) if rel.endswith("package.json") else text.splitlines()
        )
        if any(D._owned_program(ln, ctx.root, files, ident) for ln in lines if ln.strip()):
            return True
    return False


def _project_config(place: str, ctx) -> bool:
    """A configuration file of the project's own (not a tool's) that its code reads."""
    from truthstone.intent import dead_switch as D

    if PurePosixPath(place).suffix.lower() not in (
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".env",
        ".py",
        ".ts",
        ".js",
    ):
        return False
    texts = [(f, ctx.text(f) or "") for f in ctx.all_files if D._is_reader(f) and not ctx.is_test(f)]
    rel = place.lstrip("./")
    return D._code_mentions_file(rel, texts)


def _external(P, PS, sents: list[str], i: int, off: int, name: str, kind: str, callee: str, ctx) -> str:
    """Why ``name`` is another program's (a short reason), or ""."""
    s = sents[i]
    prev = sents[i - 1] if i else ""
    nxt = sents[i + 1] if i + 1 < len(sents) else ""
    if P._external(name) or PS._fixed_external(name):
        return "external-list"
    if (
        kind == "env"
        and (P._WELL_KNOWN_ENV.match(name) or _well_known(name))
        and not _convention_owned(P, PS, s, off, name, ctx)
    ):
        return "well-known-env"
    if kind == "env" and _SECRET.search(name):
        return "credential-or-endpoint"
    if kind == "env" and not _project_prefixed(name, ctx):
        from truthstone.intent import dead_switch as D

        head = name.split("_", 1)[0]
        if _TOOLS.fullmatch(head) or D._dependency_owned(name, D.project_identity(ctx.root, ctx.files)):
            return "tool-or-dependency-prefix"
    if _ERROR_CONTEXT.search(s[max(0, off - 60) : off]) or _ERROR_AFTER.match(
        s[off + len(name) : off + len(name) + 30]
    ):
        return "error-text"
    if _other_subject(PS, s, off, name, ctx):
        return "other-subject"
    if any(
        a <= off < b
        for a, b in [m.span() for m in PS._TOOL_CMD.finditer(s) if not PS._PROJECT_RUN.fullmatch(m.group(0))]
    ):
        return "tool-command"
    if _FORWARDS.search(s) or _FORWARDS.search(nxt) or _FORWARDS.search(prev):
        return "forwarded"
    owner = _owner(PS, s, off, name, kind, callee, ctx) if kind in ("kw", "key", "name") else ""
    if owner == "lib":
        return "library-call"
    if owner:
        return ""  # handed to the project's own callable, which does not pass it on: the project's switch
    blank = _FILE_TOKEN.sub(" ", _CODE_SPANS.sub(lambda m: " " if name in m.group(0) else m.group(0), s))
    blank = re.sub(r"\([^)]{0,200}\)", " ", blank)  # what a parenthesis says the switch does is not its owner
    tool_text = PS._PLACE_PHRASE.sub(" ", PS._PROJECT_RUN.sub(" ", blank))
    if kind == "env":
        cstart, cend = _clause_bounds(s, off, len(name))
        tool_text = PS._PLACE_PHRASE.sub(" ", _FILE_TOKEN.sub(" ", s[cstart:cend].replace(name, " ")))
        tool_text = _ENV_PLACES.sub(" ", tool_text)
    if kind != "env" or not _project_prefixed(name, ctx):
        nouns = _TOOL_NOUN.search(tool_text) if kind != "env" else None
        if (_TOOLS.search(tool_text) or nouns) and not _own_subject(PS, s, ctx):
            return "tool-named"
        prev_text = PS._PLACE_PHRASE.sub(" ", _FILE_TOKEN.sub(" ", prev))
        picked_up = re.match(_PICKS_UP, s, re.I) or re.search(
            r"\b(?:them|they|it|its|their)\b", s[:off], re.I
        )
        if (
            prev
            and (_TOOLS.search(prev_text) or _TOOL_NOUN.search(prev_text))
            and not _own_subject(PS, s, ctx)
            and picked_up
        ):
            return "tool-named-before"
    if (
        PS._EXTERNAL_SERVICE.search(blank)
        and not _OWN_SERVICE.search(s)
        and not (kind == "env" and _project_prefixed(name, ctx))
    ):
        return "service"
    if kind in ("kw", "key", "name"):
        if (
            PS._LIB_IN_SENTENCE(s)
            or _LIB_SAID.search(blank)
            or (prev and _LIB_SAID.search(_FILE_TOKEN.sub(" ", prev)))
        ):
            return "library-said"
        packages = ctx.packages()
        if packages and (P.library_api(name, s, packages) or _mentions_package(blank, packages)):
            return "library"
    if kind == "flag":
        prog = _flag_program(s, off)
        if prog and PS._TOOL_CMD.search(f"`{prog} `"):
            return "tool-command"
        why = _flag_place_program(s, name, ctx)
        if why:
            return why
    if kind in ("key", "name", "dotted", "kw"):
        for f in _PLACE_ANY.findall(s):
            stem = re.split(r"[._-]", PurePosixPath(f).name.lower())[0]
            if _TOOLS.fullmatch(stem) or (stem.endswith("config") and _TOOLS.fullmatch(stem[:-6])):
                return "tool-named-file"
    if kind in ("key", "name"):
        why = _library_file(s, name, ctx)
        if why:
            return why
    if kind in ("key", "name", "dotted"):
        place = _named_place(s)
        tool_place = place and (
            P._tool_owned(place) or PS._CI_FILE.match(place) or PS._COMPOSE_FILE.match(place)
        )
        if tool_place and not (
            (kind == "dotted" and _own_head(name, ctx)) or _own_section_named(s, place, ctx)
        ):
            return "tool-owned-place"
    if kind == "dotted" and not _own_head(name, ctx):
        return "dotted-not-own"
    return ""


_ERROR_CONTEXT = re.compile(
    r"\b(?:fail(?:s|ed|ing)?\s+with|error(?:s|ed)?|exception|raised|thrown|crash(?:es|ed)?\s+with"
    r"|dies\s+with|aborts?\s+with|error\s+code|exit\s+code|status|message|says|prints|complains?|warning)\s*[:]?\s*[`'\"]?$",
    re.I,
)
_ERROR_AFTER = re.compile(r"^[`'\"]?\s*(?:error|exception|warning|errors)\b", re.I)


_PLACE_ANY = re.compile(
    r"(?<![\w@/-])((?:[\w.-]+/)*[\w-]+(?:\.[\w-]+)*\.(?:py|conf|cfg|ini|toml|ya?ml|json|js|ts|rc))(?![\w/-])"
)


# A sentence that carries on from the one before (a pronoun, a polite request, a bare imperative).
_PICKS_UP = (
    r"^\W*(?:(?:so|and|then|please|also)\W+)*(?:(?:can|could|would|will)\s+you\b|it\b|that\b|this\b"
    r"|raise|lower|set|pass|add|use|turn|enable|bump|increase|decrease)"
)
_ENV_PLACES = re.compile(
    r"\b(?:docker(?:file)?|compose|image|container|service|job|step|workflow|pipeline|ci|cron(?:tab)?|systemd|unit"
    r"|makefile|procfile|script|env\s+file|environment|deployment|pod|helm\s+chart|k8s|kubernetes)s?\b",
    re.I,
)


_FILE_TOKEN = re.compile(
    r"(?<![\w@])(?:[\w.-]+/)*[\w-]+\.(?:json|jsonc|toml|ya?ml|ini|cfg|conf|env|py|ts|js|mjs|cjs|sh|lock|md|txt)\b"
)


def _mentions_package(s: str, packages: set[str]) -> bool:
    blank = _CODE_SPANS.sub(lambda m: " " + m.group(0).strip("`") + " ", s)
    return any(
        re.search(rf"(?<![\w-]){re.escape(p)}(?:'s)?(?![\w-])", blank, re.I) for p in packages if len(p) >= 3
    )


def _call_target(s: str, off: int, name: str) -> str:
    """The callable or class the option is handed to: "pass `n=1` to `f()`", "to the `X`", "`f()`'s `n`
    option", "`X`'s `n` option", "construct the `X` with `n=1`". Not "use that in `f()`" (where the call is
    made)."""
    end = max(_span_end(s, off), off + len(name))
    after = s[end : end + 120]
    m = re.match(
        r"^[`'\"]?\s*(?:\([^)]{0,80}\)\s*)?(?:keyword\s+|option\s+|argument\s+|flag\s+)?(?:to|into)\s+(?:the\s+|a\s+|an\s+|its\s+)?"
        r"`@?([A-Za-z_][\w.]*)(?:\(\))?`",
        after,
    )
    if m:
        return m.group(1)
    m = re.match(
        r"^[`'\"]?\s*(?:keyword\s+|option\s+|argument\s+)?(?:to|into)\s+(?:the\s+)?@?([A-Za-z_][\w.]*)\(\)",
        after,
    )
    if m:
        return m.group(1)
    before = s[max(0, off - 120) : off]
    m = re.search(r"`@?([A-Za-z_][\w.]*)(?:\(\))?`(?:'s)\s+(?:[\w`]+\s+){0,2}[`'\"]?$", before)
    if m:
        return m.group(1)
    m = re.search(r"\b@?([A-Za-z_][\w.]*)\(\)(?:'s)\s+(?:[\w`]+\s+){0,2}[`'\"]?$", before)
    if m:
        return m.group(1)
    m = re.search(
        r"\b(?:construct|create|instantiate|build|make|initiali[sz]e|call|invoke|new)\s+(?:the\s+|a\s+|an\s+|its\s+)?"
        r"(?:[\w`'.]+'s\s+)?`@?([A-Za-z_][\w.]*)(?:\(\))?`\s+(?:[\w`]+\s+){0,2}?with\s+[`'\"]?$",
        before,
        re.I,
    )
    if m:
        return m.group(1)
    return ""


_SCRIPT_REF = re.compile(
    r"(?<![\w@])((?:[\w.-]+/)*[\w.-]+\.(?:sh|bash|py|ts|js|mjs|cjs)|bin/[\w.-]+)(?![\w/-])"
)
_PLACE_FILE = re.compile(
    r"(?<![\w@/-])((?:[\w.-]+/)*(?:Dockerfile[\w.-]*|Makefile|makefile|Procfile|crontab|[\w.-]+\.service"
    r"|package\.json|(?:docker-)?compose[\w.-]*\.ya?ml|[\w.-]+\.sh))(?![\w/-])"
)


def _flag_place_program(s: str, name: str, ctx) -> str:
    """Repository evidence for whose a flag is. A script the sentence hands the flag to that forwards its
    arguments ("$@", sys.argv, ...) hands it on: another program's. A place file the sentence names
    (Dockerfile, Procfile, Makefile, package.json, a .service, a shell script) whose command lines run only
    other programs (gunicorn, uvicorn, celery, docker ...) and none of the project's own: another program's.
    """
    from truthstone.intent import dead_switch as D

    files = set(ctx.all_files)
    for m in _SCRIPT_REF.finditer(s):
        rel = m.group(1).lstrip("./")
        if rel in files:
            text = ctx.text(rel) or ""
            if D._forwards_text(text) or (
                (rel.endswith((".sh", ".bash")) or rel.startswith("bin/")) and D._SHELL_FORWARDS.search(text)
            ):
                return "script-forwards"
    places = [m.group(1) for m in _PLACE_FILE.finditer(s)]
    if not places:
        return ""
    ident = D.project_identity(ctx.root, ctx.files)
    for rel in places:
        rel = rel.lstrip("./")
        if rel not in files:
            hits = [f for f in files if PurePosixPath(f).name == PurePosixPath(rel).name]
            if len(hits) != 1:
                continue
            rel = hits[0]
        text = ctx.text(rel) or ""
        lines = (
            D._package_script_lines(text.splitlines()) if rel.endswith("package.json") else text.splitlines()
        )
        programs = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
        owned = any(D._owned_program(ln, ctx.root, files, ident) for ln in programs)
        tooled = any(PS_TOOL_LINE.search(ln) for ln in programs)
        if tooled and not owned:
            return "place-runs-a-tool"
    return ""


def _library_file(s: str, name: str, ctx) -> str:
    """A project configuration file the request puts the key in, which the code hands whole to a library
    (`dictConfig(json.load(f))`, `Redis(**cfg)`) and reads no key of by name: the key is the library's
    (the dead-switch rule's section ownership, `intent/dead_switch.py`)."""
    from truthstone.intent import dead_switch as D

    place = _named_place(s)
    if not place or PurePosixPath(place).suffix.lower() not in (
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
    ):
        return ""
    rel = place.lstrip("./")
    files = set(ctx.all_files)
    if rel not in files:
        hits = [f for f in files if f.endswith("/" + rel) or PurePosixPath(f).name == PurePosixPath(rel).name]
        if len(hits) != 1:
            return ""
        rel = hits[0]
    texts = [(f, ctx.text(f) or "") for f in ctx.all_files if D._is_reader(f)]
    if not D._code_mentions_file(rel, texts):
        return ""
    try:
        owned = D._section_owned(ctx.root, rel, name, ctx.prompt, texts)
    except Exception:  # noqa: BLE001 - cannot tell: the project's
        return ""
    return "" if owned else "file-handed-to-library"


PS_TOOL_LINE = re.compile(
    r"(?:^|[\s\[\"'=:])(?:gunicorn|uvicorn|hypercorn|celery|daphne|waitress|nginx|caddy|httpd|postgres|redis-server|mysqld"
    r"|docker|kubectl|helm|terraform|pytest|jest|vitest|mocha|tsc|eslint|prettier|webpack|vite|esbuild|rollup|ruff|mypy"
    r"|black|flake8|pylint|coverage|tox|nox|pip|npm|npx|yarn|pnpm|bun|deno|cargo|go|java|mvn|gradle|dotnet|rsync|curl"
    r"|wget|sqlite3|psql|mysql|redis-cli|aws|gcloud|az|gh|git|make|supervisord|pm2|nodemon|ts-node|tsx)\b(?![./-])"
)


def _flag_program(s: str, off: int) -> str:
    before = s[max(0, off - 80) : off]
    m = re.search(r"`([^`]*)$", before)
    if m:
        return m.group(1).strip().split(" ")[0] if m.group(1).strip() else ""
    return ""


def _named_place(s: str) -> str:
    m = re.search(
        r"(?<![\w@/-])((?:[\w.-]+/)*(?:[\w.-]+\.(?:toml|json|jsonc|ya?ml|ini|cfg|conf|env|properties)|Dockerfile[\w.-]*"
        r"|Makefile|package\.json|pyproject\.toml|tsconfig[\w.-]*\.json))(?![\w/-])",
        s,
    )
    return m.group(1) if m else ""


def _own_section_named(s: str, place: str, ctx) -> bool:
    """ "in the `x` block of package.json", "under `[tool.x]` in pyproject.toml": the project's own section of
    its manifest, named after the project."""
    from truthstone.intent import dead_switch as D

    if PurePosixPath(place).name not in ("package.json", "pyproject.toml"):
        return False
    ident = D.project_identity(ctx.root, ctx.files)
    for own in set(ctx.project_names()) | set(ident["packages"]) | set(ident["commands"]):
        e = re.escape(own)
        if re.search(
            rf"\[tool\.{e}\]|[`'\"]{e}[`'\"]\s+(?:block|section|object|table|entry|key)\b|\b(?:block|section|table)\s+[`'\"]?{e}\b",
            s,
            re.I,
        ):
            return True
    return False


def _project_prefixed(name: str, ctx) -> bool:
    head = name.split("_", 1)[0].lower()
    names = {re.sub(r"[^a-z0-9]", "", n.lower()) for n in ctx.project_names()}
    return (
        bool(head)
        and len(head) >= 3
        and any(n == head or (n.startswith(head) and len(head) >= 5) for n in names)
    )


def _own_head(name: str, ctx) -> bool:
    head = name.split(".", 1)[0].lower()
    return head in {n.lower() for n in ctx.project_names()}


def _own_subject(PS, s: str, ctx) -> bool:
    subj = PS._subject(s)
    return bool(subj.kind == "token" and subj.token and subj.token.lower() in ctx.project_names())


def _well_known(name: str) -> bool:
    from truthstone.validate import config_reads

    return config_reads.is_well_known(name)


def _runtime_dependencies(root: Path) -> bool | None:
    """Whether the project declares runtime dependencies (None: cannot tell)."""
    try:
        pj = root / "package.json"
        py = root / "pyproject.toml"
        found = False
        if pj.is_file():
            data = json.loads(pj.read_text(encoding="utf-8"))
            found = True
            if data.get("dependencies") or data.get("peerDependencies") or data.get("optionalDependencies"):
                return True
        if py.is_file():
            data = tomllib.loads(py.read_text(encoding="utf-8"))
            found = True
            project = data.get("project") or {}
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            if project.get("dependencies") or [k for k in poetry if k.lower() != "python"]:
                return True
        if (root / "requirements.txt").is_file():
            return True
        return False if found else None
    except Exception:  # noqa: BLE001 - an unreadable manifest: cannot tell
        return None


def _convention_owned(P, PS, s: str, off: int, name: str, ctx) -> bool:
    """A program-implemented convention (colour, pager, editor) the request says the project's own program
    honours: "<project> honours `N` ...". Only when nothing the project runs could read it for the program:
    no runtime dependency, no colour- or pager-aware runtime call in the code."""
    if name not in _CONVENTIONS:
        return False
    cstart, _ = _clause_bounds(s, off, len(name))
    lead = s[cstart:off]
    subj = PS._subject(lead) if lead.strip() else None
    if subj is None or subj.kind != "token" or not subj.token:
        return False
    if subj.token.lower() not in ctx.project_names():
        return False
    if not _PRESENT_READ.match(lead[subj.end :]):
        return False
    if _runtime_dependencies(ctx.root) is not False:
        return False
    return all(not _CONVENTION_READERS.search(ctx.text(rel) or "") for rel in ctx.code_files())


# -- the repository --------------------------------------------------------------------------------------


_PREFIX_LITERAL = re.compile(r"[\"'`]([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_)(?:[\"'`]|\$\{|\{)")


def _suffix_known(name: str, prefix: str, ctx) -> bool:
    """Whether the part of ``name`` after ``prefix`` names something the repository has, quoted in some file
    (a flag key, an id, a field): `X_SEARCH_V2` for a `"search-v2"`."""
    suffix = name[len(prefix) :]
    words = [w.lower() for w in suffix.split("_") if w]
    if not words:
        return False
    forms = {
        "_".join(words),
        "-".join(words),
        ".".join(words),
        words[0] + "".join(w.title() for w in words[1:]),
        "".join(words),
        suffix,
    }
    for rel in ctx.all_files:
        text = ctx.text(rel) or ""
        for f in forms:
            if not f:
                continue
            if re.search(rf"[\"']{re.escape(f)}[\"']", text, re.I):
                return True
            if len(f) >= 5 and re.search(
                rf"(?<![\w.$-]){re.escape(f)}\s*[:=](?!=)|\.{re.escape(f)}\b", text, re.I
            ):
                return True
    return False


def _prefix_read(name: str, ctx) -> bool:
    """An env name read through a computed prefix (`PREFIX_${key}`, f"PREFIX_{key}", startswith("PREFIX_")) is
    read when its suffix names something the repository has (a key, an id, a word quoted in a data file)."""
    parts = name.split("_")
    prefixes = ["_".join(parts[:k]) + "_" for k in range(1, len(parts))]
    hit = ""
    for rel in ctx.code_files():
        text = ctx.text(rel) or ""
        for p in prefixes:
            if re.search(rf"[\"'`]{re.escape(p)}(?:\$\{{|\{{|[\"'`]\s*[+%]|[\"'`]\s*\))", text) or re.search(
                rf"startswith\(\s*[\"']{re.escape(p)}", text
            ):
                hit = p if len(p) > len(hit) else hit
    if not hit:
        return False
    suffix = name[len(hit) :]
    words = [w.lower() for w in suffix.split("_") if w]
    forms = {
        "_".join(words),
        "-".join(words),
        words[0] + "".join(w.title() for w in words[1:]) if words else "",
        "".join(words),
        suffix,
    }
    forms = {f for f in forms if f}
    for rel in ctx.all_files:
        text = ctx.text(rel) or ""
        for f in forms:
            if re.search(rf"[\"']{re.escape(f)}[\"']", text, re.I):
                return True
    return False


_CHILD_ENV = re.compile(
    r"(?:spawn\w*|exec\w*|fork|execa\w*|subprocess\.\w+|Popen|os\.exec\w*|os\.spawn\w*|child_process\.\w+)"
    r"\s*\([^;]{0,300}?\benv\s*[=:]",
    re.S,
)
_ENV_SUBSCRIPT = re.compile(r"\b(?:env|environ|environment|vars)\s*(?:\[\s*|\.get\(\s*)(?![\"'\d`])[A-Za-z_]")


def _env_read(name: str, ctx) -> bool:
    """An env name read without being spelled: the whole environment iterated, handed to a child process or
    read through a variable key; a settings class or prefix option; or a computed prefix (`X_${key}`) whose
    suffix the repository has. Handing `process.env` to the project's own function, which reads names
    literally, is not."""
    from truthstone.intent import dead_switch as D
    from truthstone.validate import config_reads

    for rel in ctx.code_files():
        text = ctx.text(rel) or ""
        if config_reads._ITERATES_ENV.search(text) and not re.search(r"\benv\s*=\s*(?:os\.)?environ\b", text):
            return True
        if _CHILD_ENV.search(text):
            return True
        if config_reads._NON_LITERAL_KEY.search(text) or config_reads._COMPUTED_KEY.search(text):
            return True  # `os.environ.get(f"X_{name}")`, `process.env[key]`: the reading line takes any name
        if _ENV_SUBSCRIPT.search(text):
            # a key built at run time: from a prefix the file spells (`ENV_PREFIX = "X_"`, then
            # `env[ENV_PREFIX + key]`), it reads only that prefix's names; with no prefix in sight, any name
            prefixes = [m.group(1) for m in _PREFIX_LITERAL.finditer(text)]
            if not prefixes:
                return True
            if any(name.startswith(pre) for pre in prefixes) and _suffix_known(
                name, max((pre for pre in prefixes if name.startswith(pre)), key=len), ctx
            ):
                return True
        if "BaseSettings" in text and config_reads.indirect_reads(text, {name}):
            return True
        for m in D._ENV_PREFIX_CALL.finditer(text):
            if name.upper().startswith(m.group(1).upper().rstrip("_") + "_"):
                return True
    return _prefix_read(name, ctx)


def _flag_read(name: str, ctx) -> bool:
    from truthstone.intent import dead_switch as D

    names = [name] + (["--" + name[5:]] if name.startswith("--no-") else [])
    for rel in ctx.all_files:
        if not ctx.wide_code(rel):
            continue
        if any(D._flag_read(ctx.text(rel) or "", n) for n in names):
            return True
    return False


def _doc_file(rel: str) -> bool:
    from truthstone.validate import spec_integrity

    return spec_integrity.is_doc_path(rel)


def relied(
    P, prompt: str, root, files, already: set[str] | None = None
) -> list[tuple[object, list[str], str]]:
    """[(Assertion, only_in, kind)] for the switch-like names the request relies on and nothing reads."""
    from truthstone.intent import premise_switch as PS

    if files is None or not prompt:
        return []
    prompt = prompt.translate(_APOS)
    sents = [s for _, s in _sentences(prompt)]
    objects = creation_objects(sents)
    picked: list[tuple[int, int, str, str, str, bool]] = []
    created: set[str] = set()
    for i, s in enumerate(sents):
        for off, name, kind, callee, valued in candidates(s):
            if _skip_name(name, kind) or _in_dquotes(s, off):
                continue
            if relied_stance(sents, i, off, name, valued) and not _made_by_object(name, objects):
                if kind == "env" and not _env_relied(sents, i, off, name, valued):
                    continue  # introduced, not relied on; not created either
                if not _used(sents, i, off, name, valued):
                    continue  # a statement, not a request that uses the switch
                picked.append((i, off, name, kind, callee, valued))
            else:
                created.add(name)
                created.add(name.lstrip("-"))
    picked = [p for p in picked if p[2] not in created and p[2].lstrip("-") not in created]
    if already:
        picked = [p for p in picked if p[2] not in already]
    if not picked:
        return []
    ctx = PS._Ctx(P, root, list(files), prompt)
    chosen: dict[str, tuple[object, str]] = {}
    for i, off, name, kind, callee, _valued in picked:
        if name in chosen:
            continue
        if _external(P, PS, sents, i, off, name, kind, callee, ctx):
            continue
        if not _anchor(P, PS, sents, i, off, name, kind, callee, ctx) and not (
            kind == "env" and _convention_owned(P, PS, sents[i], off, name, ctx)
        ):
            continue
        leaf = name.rpartition(".")[2] if kind == "dotted" else name
        if kind == "flag":
            keys: tuple[str, ...] = (name,)
        else:
            keys = tuple(dict.fromkeys((leaf, leaf.replace("-", "_"), *PS._variants(leaf))))
        # resolved as a plain name: the env and flag reads that are not spelled are judged below
        a = P.Assertion(name, "name", keys, existing=True)
        chosen[name] = (a, kind)
        if len(chosen) >= MAX_NAMES:
            break
    if not chosen:
        return []
    unbacked = P.resolve(
        [a for a, _ in chosen.values()],
        Path(root),
        list(files),
        code_suffixes=frozenset(P._CODE_SUFFIXES | PS._EXTRA_SUFFIXES),
        switch_kinds=frozenset(P._SWITCH_KINDS | {"symbol"}),
    )
    out = []
    for a, only in unbacked:
        kind = chosen[a.name][1]
        if only and not all(PS._note_file(p, set()) if kind == "env" else _doc_file(p) for p in only):
            continue  # a config, data or CI file has it: something may read it
        if kind == "env" and _env_read(a.name, ctx):
            continue
        if kind == "flag" and _flag_read(a.name, ctx):
            continue
        final = P.Assertion(a.name, {"env": "env", "flag": "flag"}.get(kind, "name"), a.keys, existing=True)
        out.append((final, only, kind))
    return out
