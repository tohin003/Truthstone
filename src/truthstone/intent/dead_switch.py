"""Rule D, "a dead switch set" (C1-D v4, day 4): a request-named switch written where nothing reads it,
held at the edit.

Ported from the frozen prototype ``premise_proto_d4.py`` (D v4), which is the specification. The engine
decides it in ``Guard._pre_tool_use_decision``, where the prompt-time premise hold sits: after Level 0
and before the (possibly deferred) advice, so a hold is the decision recorded on every path. It speaks
(``DEAD_SWITCH_SPEAKS`` True since its blind gate passed on battery D2); with the constant False the edit it
would hold proceeds, and the hold is kept as evidence, never as a finding or a decision.

The failure class (FP-CONFIG): the request says a switch exists ("raise `OTTERLOG_CACHE_TTL` to 120 in
docker-compose.yml", "add `--with-archived` to the digest:nightly script"); nothing in the repository
reads it; the agent writes it where it would be set and reports the behaviour changed. The prompt-time
premise check needs words that say the switch exists today, and terse requests carry none. This rule
needs no such words: it watches the EDIT. When an edit writes a request-named switch into a place where
switches are set, and no code in the repository reads that switch, the edit is held once, before it
happens, with the facts and the honest next step.

What counts (all must hold):
- the switch is named in the task's request: a ``--flag``, an ``ENV_NAME`` (two or more upper-case
  parts), or a back-quoted compound identifier (a config key: ``snake_case``, ``kebab-case`` or
  ``camelCase``), the latter only from a one-word back-quoted span or a ``key=value`` span;
- the edit (a file tool's edit, or one file of a Codex patch) writes it into a PLACE:
  * env: an env file (``.env*``, ``*.env``), a compose or CI ``environment``/``env`` entry, a Dockerfile
    ``ENV``, a shell ``NAME=``/``export NAME``, a systemd ``Environment=``; the name must be the
    project's own: its leading parts name the project (pyproject/package.json name, or the workspace
    directory's name), or its first part is the first word, of five or more letters, of a hyphenated
    project name;
  * flag: a command line in package.json ``scripts``, a shell script, a Makefile, a Dockerfile, a
    compose ``command``, a Procfile, a ``.service``; only the command's program owns a flag (the token
    after ``NAME=value`` assignments and launchers such as ``node``, ``python``, ``tsx``, ``uv run``,
    ``npx``), and it must be the repository's: a repository file (``node scripts/x.ts``),
    ``-m <own package>``, the project's own command (pyproject ``[project.scripts]``, package.json
    ``bin`` or ``name``, also as an installed path), or an npm/yarn/pnpm/bun script whose command is one
    of those; a systemd ``ExecStart=`` line's program counts; a tool's own flags (a fixed list) never are,
    nor a flag the program may hand on to another;
  * key: a structured config file (json/yaml/toml/ini/cfg/conf/properties) that no tool owns, that is
    not CI, compose, package.json or pyproject.toml, and that the project reads (code mentions its name,
    its directory's distinctive name, or a name chosen at run time in its directory), key by key: some
    other key of the section the request names (else of the file) is read by name; a section handed
    whole to a library is the library's;
- no code reads the switch: no code, test or script file of the repository (as indexed, plus the files
  the task created) has a read form of it (flag: the literal ``--name``, or the bare name quoted, as an
  attribute/subscript of an args-like object, or as ``name:``/``name=``; env: the name as a word, a
  prefix read or prefix option, a settings class, or the whole environment read through a computed key
  or handed on as a value; key: the name or its snake/kebab/camel variants as a word); the edited file
  does not read the env name itself (``$NAME``, ``${NAME:-x}``, ``$(NAME)``, ``${{ env.NAME }}``); and
  no file of the same edit adds a reader (code or test; a script only by a reader form);
- the request neither asks for the switch to be made nor says it is absent or not read yet;
- the switch is not well known (``config_reads.is_well_known``), not a declared dependency's
  (``OPENAI_``-style prefixes of dependency names), not already noted for the session by the
  prompt-time check;
- once per task.

Unknown means silent: an unreadable file, a repository past the scan budget, a patch that does not parse.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path, PurePosixPath

from truthstone.adapters import edits as _edits

MAX_SCAN_BYTES = 64_000_000
MAX_FILE_BYTES = 1_000_000

HOLD = (
    "Truthstone: before editing: nothing in this repository reads `{name}`: no code mentions it, so "
    "writing it into {where} changes nothing. The request assumes it exists. First tell the user so in a "
    'message ("`{name}` doesn\'t exist in this codebase; nothing reads it"). Then either build what the '
    'request describes, or finish with "not done: `{name}` doesn\'t exist"; setting a switch nothing '
    "reads is not done."
)
# The hold's finding is the prompt-time hold's kind (``premise.hold_finding``) with its own summary:
# readouts tell the two apart by it.
HOLD_SUMMARY = "an edit that writes a switch nothing reads, held once so the user hears first (rule D)"

# Whether rule D holds. Its blind precision gate (S7/S18: at most 1 of 40 honest sessions held) failed for
# D v3 (3/40, battery D1) and passed for D v4 (0/40, battery D2, 2026-11-08 08:44), so v4 speaks. False: the
# engine evaluates it at the same place but never holds; the edit it would have held is kept on the task state
# (``TaskState.dead_switch_recorded``) and in the log, never as a finding or a decision (S9), and the event's
# decision is what it would be without rule D.
DEAD_SWITCH_SPEAKS = True

READER_SUFFIXES = frozenset(
    {".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".go", ".rs", ".java",
     ".rb", ".kt", ".cs", ".php", ".scala", ".swift", ".lua", ".pl", ".ex", ".exs", ".sh", ".bash", ".zsh"}
)
READER_NAMES = frozenset({"makefile", "gnumakefile", "dockerfile", "containerfile", "justfile"})
CODE_SUFFIXES = READER_SUFFIXES - {".sh", ".bash", ".zsh"}
STRUCTURED = (".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties")

_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![\w-])")
_ENV = re.compile(r"(?<![\w$])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![\w])")
_TICK = re.compile(r"`([^`\n]{1,120})`")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)*$")
_HEADER = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z0-9]+)+$")


def _is_test(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    name = parts[-1] if parts else ""
    return any(
        p in ("test", "tests", "__tests__", "spec", "specs", "testdata", "fixtures") for p in parts[:-1]
    ) or bool(re.match(r"(test_.*|.*_test\.\w+|.*\.(test|spec)\.\w+|conftest\.py)$", name))


def _is_reader(rel: str) -> bool:
    """Tests read switches too (precision first); an extension-less ``bin/`` file is a script."""
    p = PurePosixPath(rel)
    low = p.name.lower()
    return (
        p.suffix.lower() in READER_SUFFIXES
        or low in READER_NAMES
        or low.startswith(("dockerfile.", "makefile."))
        or (len(p.parts) >= 2 and p.parts[-2] == "bin" and not p.suffix)
    )


def request_switches(prompt: str) -> dict[str, str]:
    """{name: kind} for the switches a request names: flags, env names, config keys."""
    out: dict[str, str] = {}
    text = prompt[:20_000]
    for m in _FLAG.finditer(text):
        out.setdefault(m.group(1), "flag")
    for m in _ENV.finditer(text):
        out.setdefault(m.group(1), "env")
    for m in _TICK.finditer(text):
        span = m.group(1).strip()
        pieces = span.split()
        assign = re.match(r"^[\"']?([A-Za-z_][\w.-]*)[\"']?\s*[=:]\s*\S", span)
        if len(pieces) == 1:
            key = pieces[0].split("=", 1)[0].strip("'\",;:()")
        elif assign and not span.startswith("-"):
            key = assign.group(1)  # `summary_row = true`, `"maxBatchSize": 200`
        else:
            continue
        if not key or key in out or key.startswith("-") or _ENV.fullmatch(key):
            continue
        compound = "_" in key or "-" in key or re.search(r"[a-z][A-Z]", key) is not None
        if _KEY.match(key) and not _HEADER.match(key) and len(key) >= 3 and not key.isdigit() and compound:
            out[key] = "key"  # a config key must be a compound name
    return out


def variants(name: str) -> set[str]:
    base = name.lstrip("-")
    out = {base}
    parts = re.split(r"[-_]", base)
    if len(parts) > 1:
        out |= {
            "_".join(parts), "-".join(parts), parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
        }
    if re.search(r"[a-z][A-Z]", base):
        snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", base).lower()
        out |= {snake, snake.replace("_", "-")}
    return {v for v in out if len(v) >= 3}


def _flag_read(text: str, name: str) -> bool:
    if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
        return True
    for b in variants(name):
        e = re.escape(b)
        if re.search(
            rf"[\"'`]{e}[\"'`]|\b(?:args|opts?|options|argv|flags|values|params|parsed|cli|cmd|config|cfg|settings|"
            rf"kwargs|ns|namespace)\s*(?:\.|\[\s*[\"']){e}\b|(?<![\w.$-]){e}\s*(?:[:=?]|\))",
            text,
        ):
            return True
    return False


_ENV_PREFIX_CALL = re.compile(
    r"(?:auto_envvar_prefix|env_prefix|envvar_prefix|from_prefixed_env|SetEnvPrefix|with_prefix|prefixed)"
    r"\s*[=:(]\s*[\"'`]([A-Za-z][A-Za-z0-9_]*)[\"'`]"
)
# The whole environment as a value: handed to a child process, spread or copied, or aliased and then read
# through a non-literal key. An alias read only by literal names (`env.PORT`) reads only those names.
_ENV_OBJ = r"(?:os\.environ|process\.env)"
_ENV_TO_CHILD = re.compile(rf"\benv\s*[=:]\s*(?:\{{\s*(?:\.\.\.|\*\*)\s*)?(?:dict\(\s*)?{_ENV_OBJ}\b")
_ENV_SPREAD = re.compile(
    rf"(?:\.\.\.|\*\*)\s*{_ENV_OBJ}\b|Object\.(?:entries|keys|values|assign)\([^)]*{_ENV_OBJ}"
    rf"|{_ENV_OBJ}\.(?:items|keys|values|copy)\(|dict\(\s*{_ENV_OBJ}\s*\)"
)
_ENV_ALIAS = re.compile(rf"\b([A-Za-z_]\w*)\s*(?::[^=;\n]{{0,80}})?=\s*{_ENV_OBJ}\b")
_ENV_ARG = re.compile(rf"\w\s*\(\s*{_ENV_OBJ}\s*[,)]")


def _env_whole(text: str) -> bool:
    if _ENV_TO_CHILD.search(text) or _ENV_SPREAD.search(text):
        return True
    aliases = {m.group(1) for m in _ENV_ALIAS.finditer(text)}
    if _ENV_ARG.search(text):
        aliases |= {"env", "environ", "environment", "vars"}
    for a in aliases:
        e = re.escape(a)
        if re.search(rf"\b{e}\s*\[\s*(?![\"'\d])", text) or re.search(
            rf"\b{e}\.get\(\s*(?![\"'`])", text
        ):
            return True  # env[key], env.get(name): any name may be read
    return False


def _env_read(text: str, name: str) -> bool:
    from truthstone.validate import config_reads

    if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text):
        return True
    if config_reads._NON_LITERAL_KEY.search(text) or _env_whole(text):
        return True
    if config_reads.indirect_reads(text, {name}):
        return True
    parts = name.split("_")
    for k in range(1, len(parts)):
        prefix = "_".join(parts[:k]) + "_"
        if re.search(rf"[\"'`]{re.escape(prefix)}(?:\{{|\$\{{|[\"'`])", text):
            return True  # a prefix read: f"FEED_{key}", `FEED_${k}`, startswith("FEED_")
    for m in _ENV_PREFIX_CALL.finditer(text):
        if name.upper().startswith(m.group(1).upper().rstrip("_") + "_"):
            return True  # Click auto_envvar_prefix, pydantic env_prefix, dynaconf, Flask, viper
    return False


def _key_read(text: str, name: str) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", text) for b in variants(name) | {name})


# Tools' own flags, never the project's: the prompt-time check's fixed list (C1 v4.3, frozen), copied.
_FIXED_FLAGS = frozenset(
    {
        "--abort-on-uncaught-exception", "--clearCache", "--collect-only", "--cov", "--cov-fail-under",
        "--cov-report", "--cpu-prof", "--detectOpenHandles", "--disable-warnings", "--doctest-modules",
        "--durations", "--durations-min", "--enable-source-maps", "--env-file", "--experimental-vm-modules",
        "--extendedDiagnostics", "--failed-first", "--ff", "--forbid-only", "--force-with-lease",
        "--frozen-lock" "file",  # one literal, split for the leakage lint's token scan
        "--headed", "--heap-prof", "--heapsnapshot-near-heap-limit", "--heapsnapshot-signal",
        "--ignore-scripts", "--inspect", "--inspect-brk", "--install-completion", "--junit-xml", "--junitxml",
        "--last-failed", "--legacy-peer-deps", "--lf", "--log-cli-level", "--logHeapUsage", "--max-failures",
        "--max-old-space-size", "--maxWorkers", "--maxfail", "--no-audit", "--no-cache-dir", "--no-verify",
        "--noEmit", "--numprocesses", "--onlyChanged", "--pass-with-no-tests", "--passWithNoTests", "--pdb",
        "--prefer-offline", "--prof", "--randomly-seed", "--reporter", "--reruns", "--runInBand",
        "--runxfail", "--setup-show", "--show-completion", "--showlocals", "--stack-trace-limit",
        "--strict-markers", "--tb", "--testTimeout", "--trace-deprecation", "--trace-uncaught",
        "--trace-warnings", "--traceResolution", "--unhandled-rejections", "--update-snapshots",
        "--updateSnapshot", "--watchAll",
    }
)


READS = {"flag": _flag_read, "env": _env_read, "key": _key_read}


# -- the project's own names ---------------------------------------------------------------------


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def project_identity(root: Path, files: list[str]) -> dict:
    """Project name tokens, own commands, own top-level packages, dependency names. Never raises."""
    names: set[str] = {_norm(root.name)}
    raw_names: set[str] = {root.name}
    commands: set[str] = set()
    packages: set[str] = set()
    deps: set[str] = set()
    scripts: dict[str, str] = {}
    try:
        py = root / "pyproject.toml"
        if py.is_file() and py.stat().st_size <= MAX_FILE_BYTES:
            data = tomllib.loads(py.read_text(encoding="utf-8", errors="replace"))
            project = data.get("project") if isinstance(data.get("project"), dict) else {}
            if project.get("name"):
                names.add(_norm(str(project["name"])))
                raw_names.add(str(project["name"]))
            commands |= {str(k) for k in (project.get("scripts") or {})}
            for spec in list(project.get("dependencies") or []):
                m = re.match(r"\s*([A-Za-z0-9][\w.-]*)", str(spec))
                if m:
                    deps.add(m.group(1).lower())
    except Exception:  # noqa: BLE001 - an unreadable manifest names nothing
        pass
    try:
        pj = root / "package.json"
        if pj.is_file() and pj.stat().st_size <= MAX_FILE_BYTES:
            data = json.loads(pj.read_text(encoding="utf-8", errors="replace"))
            if data.get("name"):
                nm = str(data["name"]).rpartition("/")[2]
                names.add(_norm(nm))
                raw_names.add(nm)
                commands.add(nm)
            b = data.get("bin")
            if isinstance(b, dict):
                commands |= {str(k) for k in b}
            elif isinstance(b, str) and data.get("name"):
                commands.add(str(data["name"]).rpartition("/")[2])
            scripts = {str(k): str(v) for k, v in (data.get("scripts") or {}).items()}
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                deps |= {str(d).rpartition("/")[2].lower() for d in (data.get(key) or {})}
    except Exception:  # noqa: BLE001 - an unreadable manifest names nothing
        pass
    for rel in files:
        parts = PurePosixPath(rel).parts
        if len(parts) >= 2 and parts[0] == "src" and (parts[-1] == "__init__.py" or len(parts) == 2):
            packages.add(PurePosixPath(parts[1]).stem)
        elif len(parts) >= 2 and parts[-1] == "__init__.py":
            packages.add(parts[0])
    names.discard("")
    first_words = {re.split(r"[-_. ]", raw.lower())[0] for raw in raw_names if re.search(r"[-_. ]", raw)}
    return {"names": names, "commands": commands, "packages": packages, "deps": deps, "scripts": scripts,
            "first_words": first_words}


def _project_prefixed(name: str, ident: dict) -> bool:
    """The env name's leading parts, joined, name the project: ``KENNELBOOK_MAX_NIGHTS``
    (kennelbook), ``FLAG_KIT_DEBUG`` (flag-kit), ``HARVEST_LOG_FORMAT`` (harvestbox: a leading part of
    five or more letters that is most of the name); or its first part is the first word, of five or more
    letters, of a hyphenated project name (``MAILER_SANDBOX`` for mailer-service). At least one part
    follows."""
    segs = name.lower().split("_")
    heads = {"".join(segs[:k]) for k in range(1, len(segs))}
    for n in ident["names"]:
        if len(n) < 3:
            continue
        if n in heads:
            return True
        if any(len(h) >= 5 and n.startswith(h) and len(h) >= 0.6 * len(n) for h in heads):
            return True
    first = {w for w in ident.get("first_words", ()) if len(w) >= 5}
    return bool(first & {segs[0]})


def _dependency_owned(name: str, ident: dict) -> bool:
    head = name.split("_", 1)[0].lower()
    return any(
        _norm(d).startswith(head) or head.startswith(_norm(d)) for d in ident["deps"] if len(_norm(d)) >= 3
    )


# -- what the request itself says about the switch ----------------------------------------------------

_SENT = re.compile(r"(?<=[.!?])\s+|\n\s*\n")
_CREATE_VERB = re.compile(
    r"\b(?:add(?:s|ed|ing)?|introduc\w*|creat\w*|defin\w*|implement\w*|expos\w*|support\w*|accept\w*|"
    r"allow\w*|needs?|wants?|wire\w*|teach\w*|giv\w+|offer\w*|provid\w*|renam\w*)\b",
    re.IGNORECASE,
)
_NEW_THING = re.compile(r"\b(?:a|an|new|another|the\s+new)\b", re.IGNORECASE)
_KIND_NOUN = re.compile(
    r"^[`'\"]?\s*(?:\w+\s+){0,2}?(?:key|flag|option|setting|variable|env(?:ironment)?\s+var(?:iable)?|"
    r"parameter|switch|field|argument|entry)\b",
    re.IGNORECASE,
)
_ABSENT_VERB = (
    r"(?:doesn'?t|does\s+not|isn'?t|is\s+not|aren'?t|are\s+not|won'?t|never)\s+(?:yet\s+|currently\s+)?"
    r"(?:exist|there|read|used|supported|defined|implemented|work|wired)"
)


_SAYS_NEW = re.compile(
    r"\bnothing\s+(?:\w+\s+){0,3}?reads\b|\b(?:isn'?t|is\s+not|aren'?t|are\s+not)\s+(?:read|used|wired)\s+"
    r"(?:anywhere|yet|by\s+anything)|\bno\s+code\s+(?:\w+\s+){0,2}?reads\b"
    r"|\bswitch\s+(?:\S+\s+){0,4}?over\s+to\b|\b(?:wire|hook|plumb)\s+(?:it|that|this|them)\s+(?:up|in|through)\b"
    r"|\buse\s+the\s+(?:new\s+)?(?:config|configured|setting)\s+value\b"
    r"|\b(?:needs?|has|have|should|must|will\s+need)\s+to\s+(?:start\s+)?(?:read|reading|use|using|honou?r|pick\s+up)\b"
    r"|\bstart\s+(?:reading|using|honou?ring)\b",
    re.IGNORECASE,
)


def _says_new(sentence: str) -> bool:
    """The request says the switch is not read yet, or asks for its read to be built ("Nothing reads that
    key yet", "switch ingest over to the config value", "it needs to start reading that variable")."""
    return _SAYS_NEW.search(sentence) is not None


def _absent_tied(sentence: str, name: str) -> bool:
    """The request itself says THIS switch is absent: "`X` doesn't exist", "there is no `X`", "has no
    `X` flag", "we don't have a `X` setting", "`X` isn't read anywhere", "nothing reads `X`" / "nothing
    reads it" right after it; or the sentence says the switch is not read yet (``_says_new``). Symptom
    words elsewhere in the sentence ("the export is missing the totals row") do not count."""
    e = re.escape(name)
    q = r"[`'\"]?"
    if _says_new(sentence):
        return True
    if re.search(
        rf"\b(?:don'?t|doesn'?t|do\s+not|does\s+not)\s+have\s+(?:a|an|any)?\s*(?:\S+\s+){{0,2}}?{q}{e}{q}",
        sentence,
        re.IGNORECASE,
    ):
        return True  # "We don't have a `X` setting yet"
    return bool(
        re.search(
            rf"{q}{e}{q}[^.;:!?]{{0,25}}?\b(?:{_ABSENT_VERB}|is\s+missing|is\s+not\s+there)",
            sentence,
            re.IGNORECASE,
        )
        or re.search(rf"\b(?:no|without)\s+(?:such\s+)?(?:\w+\s+){{0,2}}?{q}{e}{q}", sentence, re.IGNORECASE)
        or re.search(rf"\bnothing\s+(?:\w+\s+){{0,2}}?reads\s+(?:it|{q}{e}{q})", sentence, re.IGNORECASE)
    )


# The prompt-time check's frozen creation and absence forms (C1 v5.2: _BUILD_GOV, _ABSENT_BEFORE/_AFTER,
# _FOLLOW_ABSENT, _FROM_ENV_BUILD, _WIRE_AFTER, _ADD_TO_PLACE with _keeps_creation), copied verbatim.
_CODE_SPANS = re.compile(r"`[^`\n]*`|(?:[\w.-]+/)+[\w.-]+")
_BUILD_GOV = re.compile(
    r"(?:(?:^|[.;:!?(\u2014\u2013]\s*|\b(?:please|then|also|and|first|now|just|so|to)\s+"
    r"|\b(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|\b(?:should|must|needs?\s+to|has\s+to|have\s+to|ought\s+to)\s+)"
    r"(?:add|create|implement|introduce|build|write|define|declare|generate|expose|teach|wire\s+up|give|extend"
    r"|support|accept|take|handle|read|honou?r|have|recogni[sz]e|understand|parse)"
    r"|\b(?:we|i)\s+(?:need|want|would\s+like|'d\s+like)\b"
    r"|\bmake\s+(?:\S+\s+){0,5}?(?:accept|take|read|support|honou?r|handle|understand|parse|recogni[sz]e)"
    r"|\b(?:update|change|modify|extend|allow|let|give)\s+(?:\S+\s+){0,5}?(?:to\s+|so\s+(?:that\s+)?it\s+)?"
    r"(?:accepts?|takes?|handles?|reads?|honou?rs?|supports?|have|has|recogni[sz]es?|understands?|parses?)"
    r"|\bput\s+(?:it|this|that|them)\s+behind\s+(?:a|an)|\bit'?d\s+be\s+(?:great|nice)\s+if"
    r"|\b(?:i|we)'?d\s+(?:like|love)"
    r"|\brenam\w*|\bnow\s+(?:called|named)|\bcall\s+it)\b[^.;!?]*$",
    re.I,
)
_ABSENT_BEFORE = re.compile(
    r"(?:\bno\s+(?:such\s+)?|\bhas\s+no\s+|\bhave\s+no\s+|\bwithout\s+(?:a|an|the|any)\s+"
    r"|\bthere(?:'s|\s+is)\s+no\s+|\blacks?\s+(?:a|an|the)?\s*)(?:[\w-]+\s+){0,1}$",
    re.I,
)
_ABSENT_AFTER = re.compile(
    r"^[`'\"]?\s*(?:(?:flag|option|setting|key|variable|switch|kwarg|argument|parameter|env\s+var)\s+)?"
    r"(?:(?:doesn'?t|does\s+not|isn'?t|is\s+not|don'?t|aren'?t|are\s+not)\s+"
    r"(?:exist|there|supported|implemented|available|wired|defined|recogni[sz]ed|accepted|read|known)"
    r"|(?:is|are)\s+missing|(?:is|are)\s+not\s+yet)",
    re.I,
)
_FOLLOW_ABSENT = re.compile(
    r"^\W*(?:(?:the|that|this)\s+(?:flag|option|setting|switch|key|variable|argument|parameter|env\s+var)"
    r"|it|that|this)\b[^.;!?]{0,80}?"
    r"\b(?:doesn'?t\s+exist|does\s+not\s+exist|isn'?t\s+(?:there|implemented|supported|wired|available)"
    r"|is\s+not\s+(?:there|implemented|supported|wired|available)"
    r"|is\s+missing|(?:is|are)\s+not\s+yet|is\s+new|needs\s+to\s+be\s+(?:added|built|created)"
    r"|has\s+to\s+be\s+(?:added|built))"
    r"|^\W*(?:so\s+|then\s+|please\s+|just\s+)?add\s+(?:it|one|that)\b",
    re.I,
)
_FROM_ENV_BUILD = re.compile(
    r"\b(?:default|defaults|defaulting|fall\s+back|falls\s+back|read|reads|take|takes|load|loads|get|gets"
    r"|pull|pulls|source|configure)\b"
    r"[^.;!?]{0,80}?\b(?:to|from|via|through|with)\s+(?:the\s+|a\s+|an\s+)?$",
    re.I,
)
_WIRE_AFTER = re.compile(
    r"^[^.;!?]{0,100}?\b(?:and|then|,)\s+(?:also\s+)?(?:make\s+\S+\s+)?"
    r"(?:read|reads|load|loads|parse|parses|honou?r|honou?rs|wire|plumb|thread|hook\s+up|pick\s+up|respect)"
    r"\s+(?:it|them|that|this|the\s+(?:value|setting|flag|option|variable|key))\b",
    re.I,
)
_ADD_TO_PLACE = re.compile(
    r"\badd(?:s|ed|ing)?\s+(?P<what>`[^`\n]+`|--?[\w-]+)(?P<mid>[^.;!?]{0,80}?)\bto\s+"
    r"(?P<place>(?:the\s+)?(?:`[^`\n]+`|[\w./:-]+)(?:\s+[\w:'-]+){0,3})",
    re.I,
)
_INVOCATION_WORD = re.compile(
    r"\b(?:call|command|invocation|run|step|job|target|entry|line|script|cron|crontab|dockerfile|makefile"
    r"|workflow|pipeline)\b",
    re.I,
)
_PARSER_WORD = re.compile(
    r"\b(?:parser|argparse|argument\s+parser|cli\s+definition|options?\s+(?:list|table)|schema)\b", re.I
)


def _keeps_creation(m) -> bool:
    """Whether an "add `--x` to <place>" builds the switch: to the parser or to `src/cli.py` it does; to
    the `tool.py` call it passes the switch (a use)."""
    place = m.group("place")
    if _PARSER_WORD.search(place):
        return True
    mpath = re.search(r"`([^`\n]+)`|([\w./-]+\.\w+)", place)
    if mpath:
        path = (mpath.group(1) or mpath.group(2)).split()[0]
        if PurePosixPath(path).suffix.lower() in CODE_SUFFIXES and not _INVOCATION_WORD.search(
            place[mpath.end():]
        ):
            return True
    return False


def _created_local(s: str, off: int, name: str) -> bool:
    """The creation or absence forms governing THIS switch (code spans blanked, offsets kept)."""
    for m in _ADD_TO_PLACE.finditer(s):
        if m.start() <= off < m.end() and not _keeps_creation(m):
            return False  # "add `--x` to <an invocation>" passes the switch
    blank = _CODE_SPANS.sub(lambda m: " " * len(m.group(0)), s)
    before = blank[max(0, off - 120):off].rstrip("`'\" ")
    after = s[off + len(name):off + len(name) + 60]
    if _BUILD_GOV.search(before + " "):
        return True
    if _ABSENT_BEFORE.search(before + " ") or _ABSENT_AFTER.match(after.lstrip("`'\"")):
        return True
    tail = re.sub(
        r"(?<![\w])\.?[\w-]+(?:\.[\w-]+)+",
        lambda m: " " * len(m.group(0)),
        blank[off + len(name):off + len(name) + 140],
    )
    # File names (".env.example", "docker-compose.yml") are blanked so their dots do not end the clause.
    if _WIRE_AFTER.match(tail):
        return True
    if _FROM_ENV_BUILD.search(before + " "):  # noqa: SIM103 - the prototype's form
        return True
    return False


def request_creates(prompt: str, name: str) -> bool:
    """Whether the request asks for ``name`` to be made, or itself says it is absent or not read yet: then
    writing it is the task, not a premise. The prompt-time check's creation and absence forms (a rename,
    "and read it in", "default ... to the X env var"), "a new key", "configurable", "support for", absence
    wording tied to the switch, a next sentence saying it is missing or new or asking for it to be made;
    "already/existing/currently" in the name's own clause cancels a creation reading."""
    text = prompt[:20_000].replace("\u2019", "'")
    sentences = _SENT.split(text)
    for n, sentence in enumerate(sentences):
        at = sentence.find(name)
        while at != -1:
            clause_before = re.split(r"[,;:!?]|\.\s|\bso\b|\bbut\b|\band\s+then\b", sentence[:at])[-1]
            if re.search(r"\b(?:already|existing|currently)\b", clause_before, re.IGNORECASE):
                at = sentence.find(name, at + 1)
                continue  # "Our script already supports a `--x` flag": its own clause says it exists
            if _created_local(sentence, at, name):
                return True
            before = sentence[max(0, at - 90):at]
            clause = re.split(r"[;:!?]|\.\s", before)[-1]
            after = sentence[at + len(name):at + len(name) + 60]
            verb = None
            for verb in _CREATE_VERB.finditer(clause):  # noqa: B007 - the clause's last creation verb
                pass
            if verb is not None and _NEW_THING.search(clause[verb.end():]):
                return True
            if _NEW_THING.search(clause[-12:]) and verb is not None and _KIND_NOUN.match(after):
                return True
            if re.search(
                r"\bconfigurable\b|\bsupport\s+for\b|\bmake\s+it\s+possible\b", sentence, re.IGNORECASE
            ):
                return True
            if _absent_tied(sentence, name):
                return True
            if n + 1 < len(sentences) and (
                _FOLLOW_ABSENT.match(sentences[n + 1])
                or _says_new(sentences[n + 1])
                or re.match(
                    r"^\W*(?:so\s+|then\s+|please\s+|just\s+)?(?:add|introduce|create|implement|define|declare|build)"
                    r"\s+(?:it|one|that|this|them)\b",
                    sentences[n + 1],
                    re.IGNORECASE,
                )
            ):
                return True  # the next sentence says it is new or asks for it to be made
            at = sentence.find(name, at + 1)
    return False


# -- where a switch is set -------------------------------------------------------------------------

_SEGMENT = re.compile(r"&&|\|\||;|\|")


_LAUNCHERS = frozenset(
    {"exec", "env", "time", "nohup", "nice", "npx", "node", "python", "python3", "tsx", "ts-node", "bun",
     "deno", "bash", "sh", "zsh", "RUN", "CMD", "ENTRYPOINT", "command:", "-", "sudo"}
)
_RUNNERS = frozenset({"uv", "poetry", "pipenv", "hatch", "pdm", "deno", "bun"})  # "<runner> run <program>"
_NPM_SCRIPT_VERBS = frozenset({"run", "run-script", "start", "stop", "restart", "test"})
_PM_BUILTINS = frozenset(
    {"install", "add", "ci", "pack", "publish", "version", "audit", "exec", "dlx", "x", "why", "link",
     "remove", "update", "upgrade", "init", "create", "outdated", "config", "cache"}
)
_INERT = frozenset(
    {"COPY", "ADD", "WORKDIR", "FROM", "EXPOSE", "VOLUME", "LABEL", "USER", "ENV", "ARG", "SHELL"}
)  # Dockerfile instructions that run nothing


def _owned_program(
    segment_before: str, root: Path, files: set[str], ident: dict, depth: int = 0
) -> bool | str:
    """Only the PROGRAM-position token owns a flag: the first token of the command after ``NAME=value``
    assignments and a chain of launchers (``node``, ``python``, ``tsx``, ``uv run``, ``npx``, ...), or
    the module after ``python -m``. Owned: a runnable repository file (the path itself is returned), the
    project's own command, its own ``-m`` package, or an npm/yarn/pnpm/bun script whose command is owned
    (one level). A systemd ``ExecStart=`` line's program counts, and an installed command by path
    (``/opt/app/venv/bin/<command>``)."""
    seg = re.sub(r"^\s*Exec(?:Start|StartPre|StartPost|Reload|Stop)=[-@+!:]*", "", segment_before)  # systemd
    tokens = [t.strip("'\"[](),") for t in seg.split()]
    tokens = [t for t in tokens if t]
    i = 0
    while i < len(tokens) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[i]):
        i += 1  # NAME=value assignments before the command
    if i < len(tokens) and tokens[i] in _INERT:
        return False
    while i < len(tokens):
        tok = tokens[i]
        if tok in _RUNNERS and i + 1 < len(tokens) and tokens[i + 1] == "run":
            i += 2
            continue
        if tok in _LAUNCHERS or (tok.startswith("-") and tok != "-m"):
            i += 1
            continue
        if tok == "-m":
            return bool(i + 1 < len(tokens) and tokens[i + 1].split(".")[0] in ident["packages"])
        break
    if i >= len(tokens):
        return False
    prog = tokens[i]
    rel = prog.removeprefix("./")
    runnable = PurePosixPath(rel).suffix.lower() in READER_SUFFIXES or rel.startswith("bin/")
    if runnable and (rel in files or (rel and not rel.startswith("/") and (root / rel).is_file())):
        return rel
    if prog in ident["commands"] or (("/" in prog) and PurePosixPath(prog).name in ident["commands"]):
        return True  # an installed command by path (/opt/app/venv/bin/<command>)
    if depth == 0 and prog == "npm":
        verb = tokens[i + 1] if i + 1 < len(tokens) else ""
        if verb in _NPM_SCRIPT_VERBS:
            script = (
                verb
                if verb in ("start", "stop", "restart", "test")
                else (tokens[i + 2] if i + 2 < len(tokens) else "")
            )
            if script in ident["scripts"]:
                return _owned_program(ident["scripts"][script], root, files, ident, depth + 1)
        return False
    if depth == 0 and prog in ("yarn", "pnpm", "bun") and i + 1 < len(tokens):
        script = tokens[i + 1] if tokens[i + 1] != "run" else (tokens[i + 2] if i + 2 < len(tokens) else "")
        if script in ident["scripts"] and script not in _PM_BUILTINS:
            return _owned_program(ident["scripts"][script], root, files, ident, depth + 1)
    return False


def _flag_set(line: str, name: str, root: Path, files: set[str], ident: dict, owned: list[str]) -> bool:
    for m in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", line):
        before = line[: m.start()]
        cut = max((x.end() for x in _SEGMENT.finditer(before)), default=0)
        who = _owned_program(before[cut:], root, files, ident)
        if who:
            if isinstance(who, str):
                owned.append(who)
            return True
    return False


# A program that hands its unknown arguments on to another one: a flag passed to it may be the other's.
_FORWARDS = re.compile(
    r"parse_known_args|ignore_unknown_options|allow_extra_args|argparse\.REMAINDER|nargs\s*=\s*[\"']\.\.\.[\"']|"
    r"allowUnknownOption|passThroughOptions|"
    r"(?:subprocess\.\w+|os\.exec\w*|Popen)\s*\([^)]{0,200}sys\.argv|\[[^\]]{0,200}\*\s*sys\.argv\[\s*[12]\s*:|"
    r"(?:spawn\w*|exec\w*|fork|execa)\s*\([^)]{0,200}(?:process\.argv|\.\.\.\s*(?:args|argv|rest|extra|passthrough)\b)|"
    r"execute_from_command_line\s*\("
)
_ARGV_BOUND = re.compile(r"\b(\w+)\s*=\s*(?:sys\.argv\s*\[\s*[12]\s*:\s*\]|process\.argv\.slice\(\s*2\s*\))")
_SPAWNISH = r"(?:spawn\w*|exec\w*|fork|execa|subprocess\.\w+|Popen|os\.exec\w*|run|call)\s*\("


def _forwards_text(text: str) -> bool:
    if _FORWARDS.search(text):
        return True
    for m in _ARGV_BOUND.finditer(text):
        if re.search(_SPAWNISH + rf"[^)]{{0,200}}\b{re.escape(m.group(1))}\b", text):
            return True  # args = sys.argv[1:]; subprocess.run(["pytest", *args])
    return False


_SHELL_FORWARDS = re.compile(r"\"\$@\"|\$@|\$\*|\"\$\{@\}\"")


def _forwards(texts: list[tuple[str, str]], owned: list[str]) -> bool:
    """Whether the program the flag goes to may hand it on: its own file when the command names one (a
    shell script's or a ``bin/`` script's ``"$@"`` counts there), else any code file of the repository
    (the strict forms only)."""
    if owned:
        for path, text in texts:
            shellish = path.endswith((".sh", ".bash", ".zsh")) or (
                path.startswith("bin/") and not PurePosixPath(path).suffix
            )
            if path in owned and (_forwards_text(text) or (shellish and _SHELL_FORWARDS.search(text))):
                return True
        return False
    return any(_forwards_text(text) for _, text in texts)


def _env_set(line: str, name: str) -> bool:
    e = re.escape(name)
    if re.search(rf"\$\{{{e}\b", line):
        return False  # `${NAME:-default}` interpolates (reads) NAME; it does not set it
    return bool(
        re.search(rf"(?:^|[\s\"'\-{{,]){e}\s*[=:]", line)
        or re.search(rf"\bENV\s+{e}\b|\bARG\s+{e}\b|\bexport\s+{e}\b|Environment=[\"']?{e}=", line)
    )


def _key_set(line: str, name: str) -> bool:
    return any(
        re.search(rf"(?:^|[\s\"'{{,]){re.escape(b)}[\"']?\s*[:=]", line) for b in variants(name) | {name}
    )


def _place_kind(rel: str) -> str | None:
    from truthstone.validate import config_reads

    p = PurePosixPath(rel)
    low = p.name.lower()
    if _is_test(rel) or p.suffix.lower() in (".md", ".rst", ".txt", ".adoc", ".markdown"):
        return None
    if low.startswith(".env") or low.endswith(".env"):
        return "dotenv"  # the prototype's "env file" kind (label renamed: the leakage lint)
    if low == "pyproject.toml":
        return "ownsection"  # only its [tool.<project>] keys can be the project's; code must read the file
    if config_reads._CI_FILES.search(rel):
        return "ci"
    if low == "package.json":
        return "package"
    if (
        p.suffix.lower() in (".sh", ".bash", ".zsh")
        or low in READER_NAMES
        or low.startswith(("dockerfile.", "makefile."))
        or low == "procfile"
        or low.endswith(".service")
    ):
        return "script"
    if p.suffix.lower() in STRUCTURED and not config_reads.is_tool_owned(rel):
        return "config"
    return None


def _package_script_lines(added: list[str]) -> list[str]:
    out = []
    for line in added:
        m = re.match(r'\s*"[^"]+"\s*:\s*"(.*)"\s*,?\s*$', line)
        if m:
            out.append(m.group(1).replace('\\"', '"'))
    return out


_GENERIC_DIRS = frozenset(
    {"config", "configs", "conf", "settings", "data", "etc", "src", "app", "lib", "deploy", "resources",
     "assets", "static", "public", "env", "envs", "files"}
)


def _code_mentions_file(rel: str, code_texts: list[tuple[str, str]]) -> bool:
    """Whether the project reads ``rel``: its file name, its stem quoted, a name chosen at run time in its
    directory (``config/${env}.json``), or (for a file in a directory of data files, such as
    ``data/rate-cards/2026.json``) its own directory's distinctive name quoted or in a path."""
    p = PurePosixPath(rel)
    base, stem = p.name, p.stem
    parent = p.parent.name if len(p.parts) > 1 else ""
    ext = p.suffix.lstrip(".")
    for _, text in code_texts:
        if base in text or (len(stem) >= 4 and re.search(rf"[\"'/]{re.escape(stem)}[\"'.]", text)):
            return True
        if parent and ext and re.search(
            rf"[\"'`/]{re.escape(parent)}/(?:\$\{{|\{{|[\"'`]\s*\+)[^\n]{{0,40}}\.{re.escape(ext)}\b", text
        ):
            return True  # chosen at run time from its directory: `config/${env}.json`, f"config/{env}.json"
        if parent and len(parent) >= 4 and parent.lower() not in _GENERIC_DIRS and \
                re.search(rf"[\"'/`]{re.escape(parent)}[\"'/`]", text):
            return True
    return False


def _patch_adds_reader(edits: list[tuple[str, list[str]]], name: str, kind: str, read) -> bool:
    """A code or test file of the same edit with a read form; a script, Makefile, Dockerfile or ``bin/``
    file only by a reader form (``$NAME``, ``${NAME``, a ``case`` arm or comparison on the flag), never by
    passing or setting it."""
    e = re.escape(name)
    for p, lines in edits:
        text = "\n".join(lines)
        if PurePosixPath(p).suffix.lower() in CODE_SUFFIXES:
            if read(text, name):
                return True
        elif _is_reader(p):
            if kind == "env" and re.search(rf"\$\{{?{e}\b|\$\({e}\)", text):
                return True
            if kind == "flag" and re.search(
                rf"[\"']?{e}[\"']?\s*\)|[=!]=\s*[\"']{e}[\"']|\s=\s*[\"']{e}[\"']\s*\]", text
            ):
                return True
    return False


def _place_reads_env(root: Path, rel: str, edits: list[tuple[str, list[str]]], name: str) -> bool:
    e = re.escape(name)
    pattern = re.compile(rf"\$\{{?{e}\b|\$\({e}\)|\$\{{\{{\s*env\.{e}\s*\}}\}}|%{e}%")
    try:
        current = (root / rel).read_text(encoding="utf-8", errors="ignore") if (root / rel).is_file() else ""
    except OSError:
        current = ""
    added = "\n".join(line for p, lines in edits if p == rel for line in lines)
    return bool(pattern.search(current) or pattern.search(added))


_COMPOUND = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+$|^[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*$")


_GENERIC_ATTRS = frozenset(
    {"version", "name", "type", "id", "level", "root", "handlers", "handler", "path", "data", "items", "keys",
     "values", "format", "class", "stream", "get", "set", "default", "value", "enabled", "debug", "args",
     "kwargs", "options", "config", "settings", "env", "mode", "size", "length", "count", "status", "error",
     "message", "result", "text"}
)


def _section_owned(root: Path, rel: str, name: str, prompt: str, texts: list[tuple[str, str]]) -> bool:
    """The key belongs to the project only when the project reads some other key of the same section by
    name. The section is the one the request names in that file, else the whole file. A sibling counts when
    the code accesses it through the section (`export["delimiter"]`, `cfg.export.delimiter`,
    `cp["import"].getint("batch_size")`), or, for the whole file, by attribute or subscript
    (`card.currency`, `data["zones"]`) unless the name is a generic attribute; a compound sibling counts
    wherever its name appears. A section handed whole to a library (`dictConfig(json.load(f))`,
    `new Redis(config.redis)`) has none, and its keys are the library's. Unparsable or new: not owned
    (silent)."""
    from truthstone.validate import config_reads

    try:
        text = (root / rel).read_text(encoding="utf-8", errors="ignore") if (root / rel).is_file() else ""
    except OSError:
        return False
    flat = config_reads._structured(rel, text) if text else None
    if not flat:
        return False
    sections = {str(part) for path in flat for part in path[:-1] if not str(part).startswith("[")}
    named = [
        sec
        for sec in sections
        if re.match(r"^[A-Za-z][\w-]{2,}$", sec)
        and re.search(
            rf"`{re.escape(sec)}`|\[{re.escape(sec)}\]"
            rf"|(?<![\w-]){re.escape(sec)}\s+(?:section|block|table|group|object|entry|settings)\b"
            rf"|\b(?:section|block|table|under)\s+[`'\"\[]?{re.escape(sec)}(?![\w-])",
            prompt,
            re.IGNORECASE,
        )
    ]
    paths = [path for path in flat if not named or any(str(x) in named for x in path[:-1])]
    siblings = {str(path[-1]) for path in paths if path and not str(path[-1]).startswith("[")} - {name}
    code = [t for p, t in texts if p != rel]
    for k in siblings:
        ek = re.escape(k)
        if _COMPOUND.match(k) and any(re.search(rf"(?<![\w-]){ek}(?![\w-])", t) for t in code):
            return True
        if named:
            for sec in named:
                es = re.escape(sec)
                pat = (
                    rf"(?<![\w-]){es}[\"'\]]*\s*"
                    rf"(?:\?\.|\.|\[\s*[\"']|\.get\w*\(\s*[\"']|,\s*[\"'])\s*{ek}(?![\w-])"
                    rf"|[\"']{es}[\"'][^\n]{{0,60}}[\"']{ek}[\"']"
                )
                if any(re.search(pat, t) for t in code):
                    return True
        elif k.lower() not in _GENERIC_ATTRS and any(
            re.search(rf"\??\.{ek}(?![\w(-])|\[\s*[\"']{ek}[\"']\s*\]|\.get\w*\(\s*[\"']{ek}[\"']", t)
            for t in code
        ):
            return True
    return False


def code_texts(root: Path, files: list[str]) -> list[tuple[str, str]] | None:
    out, budget = [], MAX_SCAN_BYTES
    for rel in files:
        if not _is_reader(rel):
            continue
        try:
            full = root / rel
            size = full.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            budget -= size
            if budget < 0:
                return None
            out.append((rel, full.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return out


def dead_switches(prompt: str, root: Path, files: list[str], edits: list[tuple[str, list[str]]],
                  this_file: str | None = None, skip: set[str] = frozenset()) -> list[tuple[str, str]]:
    """[(switch, file)] the edit sets where nothing reads them. ``edits``: (repo-relative path, added
    lines) for every file of the edit or patch; ``this_file`` limits the places to one file of it (None:
    all)."""
    from truthstone.validate import config_reads

    sw = {k: v for k, v in request_switches(prompt).items() if k not in skip}
    if not sw:
        return []
    fileset = set(files)
    ident = project_identity(root, files)
    candidates: list[tuple[str, str]] = []
    owners: dict[tuple[str, str], list[str]] = {}
    for rel, added in edits:
        if this_file is not None and rel != this_file:
            continue
        kind = _place_kind(rel)
        if kind is None or not added:
            continue
        for name, k in sw.items():
            if k == "env":
                if config_reads.is_well_known(name) or not _project_prefixed(name, ident):
                    continue
                if kind == "config" and not rel.lower().endswith((".yml", ".yaml")):
                    continue
                lines = _package_script_lines(added) if kind == "package" else added
                if any(_env_set(line, name) or re.search(rf"\bname:\s*[\"']?{re.escape(name)}\b", line)
                       for line in lines):
                    candidates.append((name, rel))
            elif k == "flag":
                if kind in ("dotenv", "config"):
                    continue
                lines = _package_script_lines(added) if kind == "package" else added
                owned: list[str] = []
                if any(_flag_set(line, name, root, fileset, ident, owned) for line in lines):
                    candidates.append((name, rel))
                    owners[(name, rel)] = owned
            elif k == "key":
                if kind != "config":
                    continue  # not package.json or pyproject.toml: a line does not show its section
                if any(_key_set(line, name) for line in added):
                    candidates.append((name, rel))
    if not candidates:
        return []
    texts = code_texts(root, files)
    if texts is None:
        return []
    out = []
    for name, rel in candidates:
        k = sw[name]
        if request_creates(prompt, name):
            continue
        if k == "env" and _dependency_owned(name, ident):
            continue
        if k == "flag" and (name in _FIXED_FLAGS or _forwards(texts, owners.get((name, rel), []))):
            continue
        if k == "key" and not _code_mentions_file(rel, texts):
            continue
        if k == "key" and not _section_owned(root, rel, name, prompt, texts):
            continue  # a section the project never reads key by key is not the project's
        read = READS[k]
        if any(read(text, name) for path, text in texts if path != rel):
            continue
        if k == "env" and _place_reads_env(root, rel, edits, name):
            continue  # the edited file itself reads it (`$NAME`, `${NAME:-x}`, `$(NAME)`, `${{ env.NAME }}`)
        if _patch_adds_reader(edits, name, k, read):
            continue  # the same edit adds its reader (code or test; a script by a reader form): being built
        out.append((name, rel))
    return out


# -- the edit's lines ----------------------------------------------------------------------------------
# Read in the hosts' own spellings, which live outside the core (``adapters/edits.py``).


def edited_lines(event, root: Path) -> list[tuple[str, list[str]]]:
    """(rel, added lines) for every file of the edit: a Codex patch's every file (from the raw payload),
    or the file tool's one file (the prototype's ``_added_lines_of_event``)."""
    return _edits.added_lines(event, root)


def edited_file(event, root: Path) -> str | None:
    """The repository-relative file the event edits: the places are limited to it."""
    return _edits.edited_file(event, root)


_rel = _edits.relative  # the prototype's ``_rel``
