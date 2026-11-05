"""Configuration nothing reads (v0.2 (e)): a named switch set, claimed to work, never read.

The failure class
-----------------
The request names a configuration switch and says it already does something ("the client
already logs every request when ``APP_TRACE=1``; switch it on for the nightly job"). The
agent sets the switch (an env entry in CI, a key in a config file, a settings constant),
checks the YAML is well formed, and reports the behaviour enabled. If nothing in the
repository reads that name, the change has no effect and the claim is false. A careful
agent's own checks cannot see it: nothing runs, nothing fails.

What is checked, deterministically
----------------------------------
At Stop, when **every** file the task changed is configuration (plus, optionally, prose),
each name the change **adds or changes the value of** is searched for in every
non-configuration file of the repository: code, scripts, tests. A name that appears
nowhere, as a whole word, is unread.

Names come from:

* env files (``.env``, ``*.env``) — every key;
* CI and compose files — the entries of ``env`` / ``environment`` / ``variables`` maps only
  (the CI system itself reads the rest);
* other YAML / TOML / JSON / INI files — the changed leaf keys;
* settings modules (``settings.py``, ``config.py``, ``constants.py``, ``conf.py``) — module
  level UPPER_CASE constants.

Precision: when it stays silent
-------------------------------
* Tool-owned configuration (``package.json``, ``tsconfig*.json``, ``pyproject.toml``,
  ``setup.cfg``, ``tox.ini``, linters, formatters, bundlers, test runners, Docker,
  ``.editorconfig``, lockfiles): the tool is the reader.
* Well-known names that runtimes and tools read (``NODE_*``, ``PYTHON*``, ``GIT_*``,
  ``GITHUB_*``, ``CI``, ``LANG``, ``TZ``, ``PATH``, ``DEBUG``, ``NO_COLOR``, ...).
* A generic consumer exists: a pydantic ``BaseSettings`` whose ``env_prefix`` the name
  starts with (or whose field it names), code that iterates over or passes on the whole
  environment, or an environment key computed from a fragment of the name.
* The request does not name it (the claim is not about it).
* Anything that cannot be read or parsed, or a repository too large to scan: silence.
"""

from __future__ import annotations

import configparser
import json
import logging
import re
import tomllib
from collections.abc import Iterable
from pathlib import PurePosixPath

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo.index import RepoIndex
from truthstone.validate import spec_integrity

log = logging.getLogger(__name__)

__all__ = ["changed_names", "concerns", "is_config_path", "is_tool_owned", "is_well_known", "unread"]

MAX_SCAN_FILES = 20_000
MAX_SCAN_BYTES = 64_000_000
MAX_FILE_BYTES = 1_000_000

# -- what counts as configuration ---------------------------------------------------------------

_CONFIG_SUFFIXES = (".yml", ".yaml", ".toml", ".json", ".ini", ".cfg", ".conf", ".properties", ".env")
_SETTINGS_MODULES = frozenset({"settings.py", "config.py", "configuration.py", "constants.py", "conf.py"})
_CI_FILES = re.compile(
    r"(^|/)(\.github/workflows/[^/]+|\.gitlab-ci\.ya?ml|azure-pipelines\.ya?ml|bitbucket-pipelines\.ya?ml|"
    r"\.circleci/config\.ya?ml|\.travis\.ya?ml|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$"
)
_TOOL_OWNED = re.compile(
    r"(^|/)("
    r"package(-lock)?\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|composer\.(json|lock)|"
    r"[jt]sconfig[^/]*\.json|pyproject\.toml|setup\.cfg|tox\.ini|pytest\.ini|mypy\.ini|\.coveragerc|\.flake8|"
    r"ruff\.toml|\.ruff\.toml|\.pylintrc|pylintrc|\.isort\.cfg|\.eslintrc[^/]*|eslint\.config\.[^/]+|"
    r"\.prettierrc[^/]*|prettier\.config\.[^/]+|\.stylelintrc[^/]*|jest\.config\.[^/]+|vitest?\.config\.[^/]+|"
    r"vite\.config\.[^/]+|webpack\.config\.[^/]+|babel\.config\.[^/]+|\.babelrc[^/]*|rollup\.config\.[^/]+|"
    r"Dockerfile[^/]*|\.dockerignore|\.editorconfig|\.pre-commit-config\.ya?ml|\.github/dependabot\.ya?ml|"
    r"renovate\.json5?|\.nvmrc|\.python-version|\.tool-versions|Cargo\.(toml|lock)|go\.(mod|sum)|Gemfile(\.lock)?|"
    r"poetry\.lock|uv\.lock|Pipfile(\.lock)?|requirements[^/]*\.txt|mkdocs\.ya?ml|\.readthedocs\.ya?ml|"
    r"codecov\.ya?ml|\.codecov\.ya?ml|netlify\.toml|vercel\.json|\.markdownlint[^/]*|\.yamllint[^/]*"
    r")$"
)


def is_tool_owned(path: str) -> bool:
    return bool(_TOOL_OWNED.search(path)) or path.endswith((".lock", "-lock.json", "-lock.yaml"))


def is_config_path(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in _SETTINGS_MODULES or name.startswith(".env") or name.endswith(".env"):
        return True
    return name.endswith(_CONFIG_SUFFIXES) or is_tool_owned(path) or bool(_CI_FILES.search(path))


# -- well-known names --------------------------------------------------------------------------

_WELL_KNOWN = re.compile(
    r"^(?:NODE|NPM|YARN|PNPM|BUN|DENO|PYTHON\w*|PIP|UV|PYTEST|POETRY|PIPENV|TOX|COVERAGE|VIRTUAL_ENV|CONDA|GIT|"
    r"GITHUB|RUNNER|ACTIONS|CI|GITLAB|CIRCLE|TRAVIS|BUILDKITE|JENKINS|DOCKER|COMPOSE|AWS|AZURE|GOOGLE|GCP|"
    r"CLOUDSDK|JAVA|MAVEN|GRADLE|CARGO|RUST\w*|GO\w*|LC|SSL|LD|DYLD|HTTP|HTTPS|NO|OTEL|SENTRY|DD|DATADOG|"
    r"PLAYWRIGHT|PUPPETEER|CHROME|JEST|VITEST|BABEL|TS_NODE|HOMEBREW)(?:_\w*)?$"
    r"|^(?:CI|LANG|LANGUAGE|TZ|HOME|PATH|USER|SHELL|TERM|PWD|TMPDIR|TEMP|TMP|EDITOR|PAGER|DEBUG|FORCE_COLOR|"
    r"NO_COLOR|COLUMNS|LINES|PORT|HOST|HOSTNAME|ENV|ENVIRONMENT|LOG_LEVEL|LOGLEVEL|DATABASE_URL|REDIS_URL|"
    r"SECRET_KEY|TOKEN|GITHUB_TOKEN)$"
)


def is_well_known(name: str) -> bool:
    """An environment name runtimes and tools read themselves (not this project's code)."""
    return bool(_WELL_KNOWN.match(name))


# -- names a change adds or changes --------------------------------------------------------------

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*?)\s*$")
_ENV_KEYS = frozenset({"env", "environment", "variables"})
_UPPER_ASSIGN = re.compile(r"^([A-Z][A-Z0-9_]{2,})\s*(?::[^=\n]+)?=\s*(.+?)\s*$", re.M)


def _flatten(value, prefix: tuple = ()) -> dict[tuple, object]:
    out: dict[tuple, object] = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            out.update(_flatten(inner, (*prefix, str(key))))
    elif isinstance(value, list):
        for position, inner in enumerate(value):
            out.update(_flatten(inner, (*prefix, f"[{position}]")))
    else:
        out[prefix] = value
    return out


def _env_lines(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def _structured(path: str, text: str) -> dict[tuple, object] | None:
    lower = path.lower()
    try:
        if lower.endswith((".yml", ".yaml")):
            import yaml

            data = yaml.safe_load(text)
        elif lower.endswith(".toml"):
            data = tomllib.loads(text)
        elif lower.endswith(".json"):
            data = json.loads(text)
        elif lower.endswith((".ini", ".cfg", ".conf", ".properties")):
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(text if text.lstrip().startswith("[") else "[default]\n" + text)
            data = {section: dict(parser[section]) for section in parser.sections()}
        else:
            return None
    except Exception:  # noqa: BLE001 - unparsable means silence
        return None
    return _flatten(data if data is not None else {})


def _ci_env(flat: dict[tuple, object]) -> dict[str, object]:
    """``env:`` / ``environment:`` / ``variables:`` entries of a CI or compose file."""
    out: dict[str, object] = {}
    for path, value in flat.items():
        for position, part in enumerate(path[:-1]):
            if part in _ENV_KEYS:
                rest = path[position + 1 :]
                if len(rest) == 1 and not rest[0].startswith("["):
                    out[rest[0]] = value
                elif len(rest) == 1 and isinstance(value, str) and "=" in value:  # compose: - KEY=value
                    key, _, inner = value.partition("=")
                    out[key.strip()] = inner
                break
    return out


def changed_names(path: str, before: str | None, after: str) -> set[str] | None:
    """Names ``path``'s change adds, or whose value it changes. None: cannot tell."""
    name = PurePosixPath(path).name
    if name in _SETTINGS_MODULES:
        old = dict(_UPPER_ASSIGN.findall(before or ""))
        new = dict(_UPPER_ASSIGN.findall(after))
        return {key for key, value in new.items() if old.get(key) != value}
    if name.startswith(".env") or name.endswith(".env"):
        old_env, new_env = _env_lines(before or ""), _env_lines(after)
        return {key for key, value in new_env.items() if old_env.get(key) != value}
    new_flat = _structured(path, after)
    old_flat = _structured(path, before) if before else {}
    if new_flat is None or old_flat is None:
        return None
    if _CI_FILES.search(path):
        old_env, new_env = _ci_env(old_flat), _ci_env(new_flat)
        return {key for key, value in new_env.items() if old_env.get(key) != value}
    changed = {key for key, value in new_flat.items() if old_flat.get(key) != value}
    return {key[-1] for key in changed if key and not key[-1].startswith("[")}


# -- whether the request says the switch works -----------------------------------------------------
#
# The unread-config check answers one premise: the request says a named switch already works
# ("acme already prints … when ACME_TRACE=1 is set, so switch that on"), the change only
# sets it, and nothing reads it. A request that asks to add, document, set or change a name
# claims nothing about what reads it today, and its readers are as often outside the repository:
# an SDK (`OPENAI_API_KEY`), a docker image (`POSTGRES_DB`), the framework (Flask's
# `MAX_CONTENT_LENGTH`), a CI action, a Dockerfile. Audit of 66e1617 (M12): 8 such requests, 16
# cells, all challenged.
_WORKS_TODAY = re.compile(
    r"\b(?:already|currently|existing|supports?|honou?rs?|respects?|picks?\s+up|"
    r"(?:is|are)\s+supposed\s+to|should\s+already)\b",
    re.IGNORECASE,
)
_REQUEST_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n\s*\n")


def claimed_to_work(request: str, name: str, external: frozenset[str] = frozenset()) -> bool:
    """Whether a sentence of ``request`` names ``name`` and says the behaviour behind it works
    today: an existing-behaviour word, or "when/if NAME=… / NAME is set" (the behaviour it gates).

    Not when the subject of the existing-behaviour word is another program — a dependency, a
    command the configuration runs (``external``): "matplotlib picks up MPLBACKEND", "psql
    respects PGPASSWORD" say what that program reads, not the repository (audit R2-6)."""
    named = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
    gate = re.compile(
        rf"\b(?:when|if|once|whenever)\s+[`'\"]?{re.escape(name)}[`'\"]?\s*(?:=|is\s+(?:set|on|true|enabled))",
        re.IGNORECASE,
    )
    # "… caps the line when the rate card has `NAME`", "if the config contains NAME": the
    # behaviour is said to follow from the file holding the name, today (day 2).
    holder = re.compile(
        rf"\b(?:when|if|once|whenever)\s+(?:(?:the|a|an|its|our|their|your)\s+)?(?:[\w./-]+\s+){{0,3}}?"
        rf"(?:has|have|contains?|defines?|includes?|sets|specifies|carries)\s+(?:(?:a|an|the)\s+)?"
        rf"(?:[\w-]+\s+)?[`'\"]?{re.escape(name)}[`'\"]?(?![\w$])",
        re.IGNORECASE,
    )
    for sentence in _REQUEST_SENTENCE.split(request[:20_000]):
        if not named.search(sentence):
            continue
        if gate.search(sentence) or holder.search(sentence):
            return True
        works = _WORKS_TODAY.search(sentence)
        if works is None:
            continue
        words = re.findall(r"[A-Za-z][\w.-]*", sentence[: works.start()])
        while words and words[-1].lower() in ("already", "currently", "still", "also", "now"):
            words.pop()
        subject = _norm_name(words[-1]) if words else ""
        if subject and subject in external:
            continue
        return True
    return False


def _norm_name(name: str) -> str:
    return name.lower().replace("-", "_").strip("`'\".,")


_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][\w.-]*)")
_COMMAND = re.compile(
    r"^\s*-?\s*run:\s*([\w./-]+)|^\s*command:\s*\[?\s*[\"']?([\w./-]+)|^\s*(?:CMD|ENTRYPOINT)\s*\[?\s*[\"']?([\w./-]+)",
    re.MULTILINE,
)


def external_programs(index: RepoIndex, texts: Iterable[str]) -> frozenset[str]:
    """The programs a request may name that are not this repository: its declared dependencies
    (pyproject, requirements, package.json) and the commands its changed configuration runs
    (CI ``run:``, compose ``command:``, ``CMD``). Never the repository's own names: its project
    name and its top-level packages and modules. Bounded; never raises."""
    found: set[str] = set()
    project: dict = {}
    try:
        root = index.root
        pyproject = root / "pyproject.toml"
        if pyproject.is_file() and pyproject.stat().st_size <= MAX_FILE_BYTES:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
            project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
            specs = list(project.get("dependencies", []) or [])
            for extra in (project.get("optional-dependencies", {}) or {}).values():
                specs += list(extra or [])
            poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
            specs += list((poetry.get("dependencies", {}) or {}).keys())
            for spec in specs:
                match = _REQUIREMENT.match(str(spec))
                if match:
                    found.add(_norm_name(match.group(1)))
        for path in list(index.files)[:MAX_SCAN_FILES]:
            base = path.rpartition("/")[2].lower()
            if base.startswith("requirements") and base.endswith(".txt"):
                full = root / path
                if full.stat().st_size <= MAX_FILE_BYTES:
                    for line in full.read_text(encoding="utf-8", errors="replace").splitlines():
                        match = _REQUIREMENT.match(line)
                        if match and not line.lstrip().startswith(("-", "#")):
                            found.add(_norm_name(match.group(1)))
        package = root / "package.json"
        if package.is_file() and package.stat().st_size <= MAX_FILE_BYTES:
            data = json.loads(package.read_text(encoding="utf-8", errors="replace"))
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                found |= {_norm_name(dep.rpartition("/")[2]) for dep in (data.get(key) or {})}
        for text in texts:
            for match in _COMMAND.finditer(text or ""):
                command = next(group for group in match.groups() if group)
                found.add(_norm_name(command.rpartition("/")[2]))
        own = {_norm_name(path.split("/", 1)[0].removesuffix(".py")) for path in index.files}
        own.add(_norm_name(str(project.get("name") or "")))
        found -= own
    except Exception:  # noqa: BLE001 - unknown means nothing is external: the claim counts
        return frozenset()
    return frozenset(found)


# -- who reads a name ----------------------------------------------------------------------------

# An environment read whose key is not a literal (`os.environ.get(var)`, `process.env[envName(k)]`)
# can be reading any name: as good as reading the whole environment.
_NON_LITERAL_KEY = re.compile(
    r"(?:\bos\.environ(?:\.get)?|\bgetenv|\bprocess\.env|\bos\.Getenv|\benv::var)\s*[\[(]\s*(?![\"'`)\]])"
)

_ITERATES_ENV = re.compile(
    r"for\s+\w+(?:\s*,\s*\w+)?\s+in\s+(?:os\.)?environ\b|(?:os\.)?environ\.(?:items|keys|values|copy)\s*\(|"
    r"dict\(\s*(?:os\.)?environ\s*\)|\*\*\s*(?:os\.)?environ\b|env\s*=\s*(?:os\.)?environ\b|"
    r"Object\.(?:keys|entries|values)\(\s*process\.env\s*\)|\.\.\.\s*process\.env\b|"
    r"for\s*\(\s*(?:const|let|var)\s+\w+\s+(?:in|of)\s+(?:Object\.\w+\()?process\.env|os\.Environ\(\)|"
    r"env::vars\(\)"
)
_COMPUTED_KEY = re.compile(
    r"(?:environ(?:\.get)?|getenv|process\.env|os\.Getenv|env::var)\s*[\[(]\s*"
    r"(?P<expr>f[\"'][^\"'\n]*[\"']|[\"'][^\"'\n]*[\"']\s*[+%]|`[^`\n]*\$\{[^`\n]*`|[A-Za-z_][\w.]*\s*\+[^\])\n]*)"
)
_ENV_PREFIX = re.compile(r"env_prefix[\"']?\s*[=:]\s*[\"']([A-Za-z0-9_]*)[\"']")
_FRAGMENT = re.compile(r"[A-Za-z0-9_]{3,}")


def indirect_reads(text: str, names: set[str]) -> set[str]:
    """The environment ``names`` a code file's ``text`` reads without spelling them — the same
    rules as :func:`_readers`: the whole environment iterated, a computed key sharing a
    fragment with the name, or a settings class (pydantic ``BaseSettings``: its ``env_prefix``,
    and fields named like the variable in lower case). Used by the prompt-time premise check
    (``intent/premise.py``), which asks the same question about a switch."""
    if not names:
        return set()
    if _ITERATES_ENV.search(text):
        return set(names)
    read: set[str] = set()
    for match in _COMPUTED_KEY.finditer(text):
        fragments = [f for f in _FRAGMENT.findall(match.group("expr")) if f.lower() not in ("get", "env")]
        read |= {name for name in names if any(f.upper() in name.upper() for f in fragments)}
    if "BaseSettings" in text:
        prefixes = [p for p in _ENV_PREFIX.findall(text) if p]
        read |= {name for name in names if any(name.upper().startswith(p.upper()) for p in prefixes)}
        read |= {
            name
            for name in names
            if re.search(rf"(?<![\w$]){re.escape(name.lower())}(?![\w$])", text)
        }
    return read


def _readers(index: RepoIndex, names: set[str], skip: set[str]) -> tuple[set[str], str]:
    """(the names some non-config file mentions, why everything is read or ""). Bounded:
    past the budget the scan says "too large", which means silence."""
    remaining = set(names)
    patterns = {name: re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])") for name in names}
    lowered = {name: re.compile(rf"(?<![\w$]){re.escape(name.lower())}(?![\w$])") for name in names}
    scanned_files = scanned_bytes = 0
    for path, record in sorted(index.files.items()):
        if path in skip or is_config_path(path) or spec_integrity.is_doc_path(path):
            continue
        if record.size > MAX_FILE_BYTES:
            continue
        scanned_files += 1
        scanned_bytes += record.size
        if scanned_files > MAX_SCAN_FILES or scanned_bytes > MAX_SCAN_BYTES:
            return set(names), "repository too large to scan"
        try:
            text = (index.root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _ITERATES_ENV.search(text) or _NON_LITERAL_KEY.search(text):
            return set(names), f"{path} reads the whole environment"
        for match in _COMPUTED_KEY.finditer(text):
            fragments = _FRAGMENT.findall(match.group("expr"))
            for name in list(remaining):
                if any(
                    fragment.upper() in name.upper()
                    for fragment in fragments
                    if fragment.lower() not in ("get", "env")
                ):
                    remaining.discard(name)
        if "BaseSettings" in text:
            for prefix in _ENV_PREFIX.findall(text):
                remaining = {
                    name for name in remaining if not (prefix and name.upper().startswith(prefix.upper()))
                }
            remaining = {name for name in remaining if not lowered[name].search(text)}
        remaining = {name for name in remaining if not patterns[name].search(text)}
        if not remaining:
            break
    return names - remaining, ""


def unread(index: RepoIndex, names: set[str], skip: set[str] = frozenset()) -> tuple[set[str], str]:
    """(the names nothing outside configuration reads, why the scan gave up or "")."""
    read, gave_up = _readers(index, names, set(skip))
    return (set() if gave_up else names - read), gave_up


# -- the concern -----------------------------------------------------------------------------------------


def concerns(state: TaskState, index: RepoIndex) -> list:
    """The unread-config concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter, baseline

    changed = sorted(state.changed_files - baseline.reverted(state, index.root))
    if not changed or any(not (is_config_path(path) or spec_integrity.is_doc_path(path)) for path in changed):
        return []  # code or tests changed too: not a config-only change
    texts = arbiter.changed_texts(state, index)
    names: dict[str, str] = {}
    for path in changed:
        if spec_integrity.is_doc_path(path) or is_tool_owned(path):
            continue
        if path not in texts:
            if path in state.deleted_files:
                continue
            return []  # a config file whose before-text is unknown: cannot tell
        before, after = texts[path]
        if after is None:
            continue
        found = changed_names(path, before, after)
        if found is None:
            return []
        for name in found:
            names.setdefault(name, path)
    request = f"{state.spec.prompt or ''}"
    external = external_programs(index, [after for _, after in texts.values() if after])
    candidates = {
        name for name in names if not is_well_known(name) and claimed_to_work(request, name, external)
    }
    if not candidates:
        return []
    nobody, gave_up = unread(index, candidates, skip=set(changed))
    if gave_up:
        log.info("truthstone: unread-config check gave up: %s", gave_up)
    if not nobody:
        return []
    shown = sorted(nobody)[:3]
    listing = ", ".join(f"`{name}`" for name in shown)
    name = shown[0]
    text = (
        f"Nothing in this repository reads {listing}, so this change has no effect; verify where "
        f"{name} is consumed before claiming the behaviour works."
    )
    finding = arbiter.finding(
        ReasonCategory.UNREAD_CONFIG,
        Severity.MEDIUM,
        summary=f"configuration nothing reads: {', '.join(shown)}",
        detail="; ".join(f"{n} in {names[n]}" for n in shown),
        evidence=[EvidenceRef(source="filesystem", path=names[n], symbol=n) for n in shown],
        mode=FailureMode.FALSE_COMPLETION,
    )
    return [arbiter.Concern(ReasonCategory.UNREAD_CONFIG, text, finding)]
