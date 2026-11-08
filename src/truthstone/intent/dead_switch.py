"""Rule D, "a dead switch set" (C1-D, day 4): a request-named switch written where nothing reads it,
held at the edit.

Ported from the frozen prototype ``premise_proto_d.py``, which is the specification. The engine
calls ``dead_switches`` from ``Guard._on_pre_tool_use``, where the prototype's ``install()`` wrapped
it.

The failure class (FP-CONFIG): the request says a switch exists ("raise `TRAMTIME_CACHE_TTL` to 120
in docker-compose.yml", "add `--with-remote` to the pages:shipping script"); nothing in the repository
reads it; the agent writes it where it would be set and reports the behaviour changed. The prompt-time
premise check needs words that say the switch exists today, and terse requests carry none. This rule
needs no such words: it watches the EDIT. When an edit writes a request-named switch into a place where
switches are set, and no code in the repository reads that switch, the edit is held once, before it
happens, with the facts and the honest next step.

What counts (all must hold):
- the switch is named in the task's request: a ``--flag``, an ``ENV_NAME`` (two or more upper-case
  parts), or a back-quoted identifier (a config key), the latter only from a one-word back-quoted span or
  a ``key=value`` span;
- the edit (a file tool's edit, or one file of a Codex patch) writes it into a PLACE:
  * env: an env file (``.env*``, ``*.env``), a compose or CI ``environment``/``env`` entry, a Dockerfile
    ``ENV``, a shell ``NAME=``/``export NAME``, a systemd ``Environment=``; the name must be the
    project's own: it starts with the project's name (pyproject/package.json name, or the workspace
    directory's name) and an underscore;
  * flag: a command line in package.json ``scripts``, a shell script, a Makefile, a Dockerfile, a
    compose ``command``, a Procfile, a ``.service``; the flag must follow, in the same command, a
    program the repository owns: a repository file (``node scripts/x.ts``), ``-m <own package>``, the
    project's own command (pyproject ``[project.scripts]``, package.json ``bin`` or ``name``), or an npm
    script whose command is one of those;
  * key: a structured config file (json/yaml/toml/ini/cfg/conf/properties) that no tool owns, that is
    not CI or compose, and whose file name some code file of the repository mentions (the project reads
    that file);
- no code reads the switch: no code file (Python, JS/TS, Go, Rust, Java, Ruby, ..., shell scripts,
  Makefile, Dockerfile; tests excluded) of the repository as it is now has a read form of it (flag: the
  literal ``--name``, or the bare name quoted, as an attribute/subscript of an args-like object, or as
  ``name:``/``name=``; env: the name as a word, or an indirect read: the whole environment, a computed
  key, a settings class; key: the name or its snake/kebab/camel variants as a word); and no code file of
  the same edit/patch adds one;
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

READER_SUFFIXES = frozenset(
    {".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".go", ".rs", ".java",
     ".rb", ".kt", ".cs", ".php", ".scala", ".swift", ".lua", ".pl", ".ex", ".exs", ".sh", ".bash", ".zsh"}
)
READER_NAMES = frozenset({"makefile", "gnumakefile", "dockerfile", "containerfile", "justfile"})
CODE_SUFFIXES = READER_SUFFIXES - {".sh", ".bash", ".zsh"}
STRUCTURED = (".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties")
SKIP_DIRS = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox", ".mypy_cache"}
)

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
    p = PurePosixPath(rel)
    low = p.name.lower()
    return (
        p.suffix.lower() in READER_SUFFIXES
        or low in READER_NAMES
        or low.startswith(("dockerfile.", "makefile."))
    ) and not _is_test(rel)


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
        if _KEY.match(key) and not _HEADER.match(key) and len(key) >= 3 and not key.isdigit():
            out[key] = "key"
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


def _env_read(text: str, name: str) -> bool:
    from truthstone.validate import config_reads

    if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text):
        return True
    if config_reads._NON_LITERAL_KEY.search(text):
        return True
    return bool(config_reads.indirect_reads(text, {name}))


def _key_read(text: str, name: str) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", text) for b in variants(name) | {name})


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
    (kennelbook), ``FLAG_KIT_DEBUG`` (flag-kit), ``MAILER_SANDBOX`` (mailer-service: its first word),
    ``HARVEST_LOG_FORMAT`` (harvestbox: a leading part of five or more letters that is most of the
    name). At least one part follows."""
    segs = name.lower().split("_")
    heads = {"".join(segs[:k]) for k in range(1, len(segs))}
    for n in ident["names"]:
        if len(n) < 3:
            continue
        if n in heads:
            return True
        if any(len(h) >= 5 and n.startswith(h) and len(h) >= 0.6 * len(n) for h in heads):
            return True
    return any(w in heads for w in ident.get("first_words", ()) if len(w) >= 4)


def _dependency_owned(name: str, ident: dict) -> bool:
    head = name.split("_", 1)[0].lower()
    return any(
        _norm(d).startswith(head) or head.startswith(_norm(d)) for d in ident["deps"] if len(_norm(d)) >= 3
    )


# -- what the request itself says about the switch ----------------------------------------------------

_SENT = re.compile(r"(?<=[.!?])\s+|\n\s*\n")
_CREATE_VERB = re.compile(
    r"\b(?:add(?:s|ed|ing)?|introduc\w*|creat\w*|defin\w*|implement\w*|expos\w*|support\w*|accept\w*|"
    r"allow\w*|need|want|wire\w*|teach\w*|giv\w+|offer\w*|provid\w*)\b",
    re.IGNORECASE,
)
_NEW_THING = re.compile(r"\b(?:a|an|new|another|the\s+new)\b", re.IGNORECASE)
_KIND_NOUN = re.compile(
    r"^[`'\"]?\s*(?:\w+\s+){0,2}?(?:key|flag|option|setting|variable|env(?:ironment)?\s+var(?:iable)?|"
    r"parameter|switch|field|argument|entry)\b",
    re.IGNORECASE,
)
_ABSENT_NEAR = re.compile(
    r"\b(?:isn'?t\s+there|is\s+not\s+there|doesn'?t\s+exist|does\s+not\s+exist|has\s+no|have\s+no|no\s+such|"
    r"not\s+yet|nothing\s+reads|isn'?t\s+read|is\s+not\s+read|doesn'?t\s+have|does\s+not\s+have|missing|"
    r"isn'?t\s+supported|is\s+not\s+supported|doesn'?t\s+support|does\s+not\s+support)\b",
    re.IGNORECASE,
)


def request_creates(prompt: str, name: str) -> bool:
    """Whether the request asks for ``name`` to be made (a new key, flag, variable; "configurable";
    "support for") or itself says it is absent: then writing it is the task, not a premise."""
    text = prompt[:20_000].replace("\u2019", "'")
    for sentence in _SENT.split(text):
        at = sentence.find(name)
        while at != -1:
            before = sentence[max(0, at - 90):at]
            clause = re.split(r"[;:!?]|\.\s", before)[-1]
            after = sentence[at + len(name):at + len(name) + 60]
            if re.search(r"\balready\b|\bexisting\b|\bcurrently\b", clause, re.IGNORECASE):
                at = sentence.find(name, at + 1)
                continue
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
            window = sentence[max(0, at - 60):at + len(name) + 60]
            if _ABSENT_NEAR.search(window):
                return True
            at = sentence.find(name, at + 1)
    return False


# -- where a switch is set -------------------------------------------------------------------------

_SEGMENT = re.compile(r"&&|\|\||;|\|")


def _owned_program(
    segment_before: str, root: Path, files: set[str], ident: dict, depth: int = 0
) -> bool | str:
    """Whether the command text before a flag runs something the repository owns: the repository file
    it runs (a path), or True for the project's own command, ``-m`` package or npm script."""
    tokens = [t.strip("'\"") for t in segment_before.split()]
    for i, tok in enumerate(tokens):
        if not tok or (tok.startswith("-") and tok != "-m"):
            continue
        if i == 0 and tok.upper() in (
            "COPY", "ADD", "WORKDIR", "FROM", "EXPOSE", "VOLUME", "LABEL", "USER", "ENV", "ARG"
        ):
            return False  # a Dockerfile instruction that runs nothing
        rel = tok.removeprefix("./")
        runnable = PurePosixPath(rel).suffix.lower() in READER_SUFFIXES or rel.startswith("bin/")
        if runnable and (rel in files or (rel and not rel.startswith("/") and (root / rel).is_file())):
            return rel
        if tok == "-m" and i + 1 < len(tokens) and tokens[i + 1].split(".")[0] in ident["packages"]:
            return True
        if tok in ident["commands"]:
            return True
        if (
            depth == 0
            and tok in ("run", "run-script")
            and i + 1 < len(tokens)
            and tokens[i + 1] in ident["scripts"]
        ):
            inner = ident["scripts"][tokens[i + 1]]
            return _owned_program(inner, root, files, ident, depth + 1)
        if (
            depth == 0
            and tok in ("npm", "yarn", "pnpm", "bun")
            and i + 1 < len(tokens)
            and tokens[i + 1] in ident["scripts"]
            and tokens[i + 1] not in ("run", "install", "test", "exec")
        ):
            return _owned_program(ident["scripts"][tokens[i + 1]], root, files, ident, depth + 1)
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
    r"(?:spawn\w*|exec\w*|fork|execa)\s*\([^)]{0,200}(?:process\.argv|\.\.\.\s*(?:args|argv|rest|extra|passthrough)\b)"
)
_SHELL_FORWARDS = re.compile(r"\"\$@\"|\$@|\$\*|\"\$\{@\}\"")


def _forwards(texts: list[tuple[str, str]], owned: list[str]) -> bool:
    """Whether the program the flag goes to may hand it on: its own file when the command names one (a
    shell script's ``"$@"`` counts there), else any code file of the repository (the strict forms only)."""
    if owned:
        for path, text in texts:
            if path in owned and (
                _FORWARDS.search(text)
                or (path.endswith((".sh", ".bash", ".zsh")) and _SHELL_FORWARDS.search(text))
            ):
                return True
        return False
    return any(_FORWARDS.search(text) for _, text in texts)


def _env_set(line: str, name: str) -> bool:
    e = re.escape(name)
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
    """Whether the project reads ``rel``: its file name, its stem quoted, or (for a file in a directory
    of data files, such as ``data/rate-cards/2026.json``) its own directory's distinctive name quoted or in
    a path."""
    p = PurePosixPath(rel)
    base, stem = p.name, p.stem
    parent = p.parent.name if len(p.parts) > 1 else ""
    for _, text in code_texts:
        if base in text or (len(stem) >= 4 and re.search(rf"[\"'/]{re.escape(stem)}[\"'.]", text)):
            return True
        if parent and len(parent) >= 4 and parent.lower() not in _GENERIC_DIRS and \
                re.search(rf"[\"'/`]{re.escape(parent)}[\"'/`]", text):
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
                own_section = kind in ("ownsection", "package")
                if kind != "config" and not own_section:
                    continue
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
        if k == "flag" and _forwards(texts, owners.get((name, rel), [])):
            continue
        if k == "key" and not _code_mentions_file(rel, texts):
            continue
        read = READS[k]
        if any(read(text, name) for path, text in texts if path != rel):
            continue
        if any(
            PurePosixPath(p).suffix.lower() in CODE_SUFFIXES and not _is_test(p) and read("\n".join(a), name)
            for p, a in edits
        ):
            continue  # the same patch adds its reader: it is being built
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
