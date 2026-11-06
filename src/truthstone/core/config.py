"""Configuration and filesystem layout.

Global config:    ~/.truthstone/config.toml
Daemon handshake: ~/.truthstone/daemon.json      (host, port, token, pid)
Shared database:  ~/.truthstone/truthstone.db
"""

from __future__ import annotations

import contextlib
import copy
import difflib
import ipaddress
import logging
import os
import re
import secrets
import stat
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, ValidationError, field_validator

from truthstone import names
from truthstone.daemon import private_paths

# Read through `names.env`, which also honours these settings under a former product name.
ENV_DISABLE = "TRUTHSTONE_DISABLE"
ENV_HOME = "TRUTHSTONE_HOME"
ENV_OBSERVE = "TRUTHSTONE_OBSERVE"
ENV_PROFILE = "TRUTHSTONE_PROFILE"
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _trusted_system_alias(path: Path, mode: int) -> bool:
    """A symlink only the system could have placed — never a user's.

    macOS's /tmp and /var aliases, and any root-owned link in a root-owned directory
    nobody else can write (Fedora Silverblue's `/home -> var/home`). One rule for every
    entry point: ``daemon/private_paths.py`` (R11).
    """
    return private_paths.trusted_system_link(str(path), mode)


def _assert_no_symlink_components(path: Path) -> None:
    """Reject a path that traverses any existing symlink component.

    Checking only the leaf directory is insufficient when a symlinked parent already
    contains the requested child.  These paths hold credentials and lifecycle state, so
    fail closed before creating or reading anything below them.
    """
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    current = candidate
    while True:
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(f"could not inspect private path component: {current}") from exc
        else:
            if stat.S_ISLNK(mode) and not _trusted_system_alias(current, mode):
                raise RuntimeError(f"refusing to use symlinked private path component: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def truthstone_home() -> Path:
    """``TRUTHSTONE_HOME``, or ``~/.truthstone``, resolved through trusted symlinks.

    An empty value means unset, exactly as the shim and the Codex hook read it
    (``environ.get(...) or default``): ``Path("")`` is the current directory, which put
    the token in the project, chmod-ed it 0700, and disagreed with the shim's home.

    Former product names count (see `names`): the setting under a former name is the
    fallback, and a former name's directory is used while only that one exists.

    A symlinked ancestor — Silverblue's `/home -> var/home`, a dotfiles manager's link —
    is resolved once, here, when root or this user placed it where nobody else can change
    it; everything downstream sees the canonical path and keeps refusing symlinks. Any
    other link leaves the path as configured, so the private-path checks refuse it. The
    shim, the Codex hook and the lifecycle helpers apply the same rule
    (``daemon/private_paths.py``), so every entry point finds the same home (R11).
    """
    raw = names.env(ENV_HOME) or ""
    home = Path(raw).expanduser() if raw else Path(names.migrated(str(Path.home() / ".truthstone")))
    return Path(private_paths.canonical_home(str(home)))


def ensure_private_dir(path: Path | None = None) -> Path:
    """Create a directory used for Truthstone credentials with owner-only access."""
    directory = Path(path or truthstone_home()).expanduser()
    _assert_no_symlink_components(directory)
    # Check every existing component we are about to traverse.  Checking only the leaf
    # still permits ``TRUTHSTONE_HOME=/tmp/user-link/truthstone`` to redirect credentials
    # through a symlinked parent.
    current = directory
    missing: list[Path] = []
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    if current.is_symlink() and not _trusted_system_alias(current, current.lstat().st_mode):
        raise RuntimeError(f"refusing to use symlinked private path component: {current}")
    directory.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
    _assert_no_symlink_components(directory)
    for component in reversed(missing):
        if component.is_symlink() or not component.is_dir():
            raise RuntimeError(f"private path component is not a directory: {component}")
    # mkdir's mode is filtered by umask and is a no-op for an existing directory.
    # Re-apply it so an old/shared installation cannot leave credentials world-readable.
    os.chmod(directory, PRIVATE_DIR_MODE)
    return directory


def write_private_text(path: Path, content: str) -> None:
    """Atomically write owner-readable text (used for local credentials/settings)."""
    path = Path(path).expanduser()
    _assert_no_symlink_components(path.parent)
    if path.is_symlink():
        raise RuntimeError(f"refusing to overwrite symlink: {path}")
    if path.parent.is_symlink():
        raise RuntimeError(f"refusing to write through symlinked directory: {path.parent}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"refusing to overwrite non-regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            # Set the mode through the already-open descriptor.  A pathname chmod
            # after close would introduce a symlink-swap window between creation and
            # replacement.
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), PRIVATE_FILE_MODE)
            else:  # pragma: no cover - legacy platforms without fchmod.
                os.chmod(tmp, PRIVATE_FILE_MODE)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def daemon_handshake_path() -> Path:
    return truthstone_home() / "daemon.json"


def database_path() -> Path:
    """One database for every project (Memory plan §1).

    Replaces the earlier per-workspace file. A single database means one retention pass,
    one maintenance schedule and one place for cross-session project memory, at the cost
    of requiring project scoping on every query — which `ProjectStore` makes structural.
    """
    return Path(names.migrated(str(truthstone_home() / "truthstone.db")))


def project_cache_dir(project_id: str) -> Path:
    return truthstone_home() / "projects" / project_id


def workspace_state_dir(workspace: str | Path) -> Path:
    """Deprecated: pre-Phase-3.5 per-workspace location, kept for cleanup only."""
    return Path(workspace).expanduser().resolve() / ".truthstone"


def _flag(name: str) -> bool:
    return names.env_flag(name)


def is_globally_disabled() -> bool:
    """Kill switch. When set, every hook path returns 'no decision' immediately."""
    return _flag(ENV_DISABLE)


def is_observe_only() -> bool:
    """Census mode. Everything is computed and recorded; nothing is ever said."""
    return _flag(ENV_OBSERVE)


def profile_override() -> Literal["minimal", "full"] | None:
    """``TRUTHSTONE_PROFILE``, when it names a profile: it wins over config.toml, as
    ``TRUTHSTONE_OBSERVE`` does (a harness or a test pins one without writing a file)."""
    value = (names.env(ENV_PROFILE) or "").strip().lower()
    if value == "minimal":
        return "minimal"
    if value == "full":
        return "full"
    return None


def token_path() -> Path:
    return truthstone_home() / "token"


def get_or_create_token() -> str:
    """A stable local credential for the daemon.

    The hook URL and its ``Authorization`` header are written into settings.json once,
    but the daemon restarts often — so the token must survive restarts rather than being
    regenerated per process. 0600, local-only, never leaves the machine.
    """
    path = token_path()
    ensure_private_dir()
    # Installers and daemon processes can ask for the token at the same time. The
    # lifecycle lock makes the read/repair/write sequence atomic, so no process can keep
    # using a token that a concurrent creator immediately replaced.
    from truthstone.daemon.lifecycle import interprocess_lock

    with interprocess_lock(path.with_name("token.lock"), timeout=2.0) as locked:
        if not locked:
            raise RuntimeError("could not acquire the Truthstone token lock")
        if path.is_symlink():
            raise RuntimeError(f"refusing to use symlink as token file: {path}")
        if path.exists():
            if not path.is_file():
                raise RuntimeError(f"refusing to use non-regular token file: {path}")
            try:
                existing = path.read_text(encoding="utf-8").strip()
                if existing:
                    os.chmod(path, PRIVATE_FILE_MODE)
                    return existing
            except OSError:
                pass
        token = secrets.token_urlsafe(32)
        write_private_text(path, token)
        return token


class DaemonSettings(BaseModel):
    """Bind address for the local daemon.

    The port is *fixed* rather than ephemeral because Claude Code's `http` hook URL is
    baked into settings.json at install time and cannot be rewritten on every daemon
    restart. `truthstone doctor` reports a conflict if something else owns the port;
    change it here and re-run `truthstone install claude`.
    """

    host: str = "127.0.0.1"
    port: int = 8787

    @field_validator("host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        """The HTTP daemon is intentionally local-only; reject network exposure."""
        host = value.strip().lower()
        if host == "localhost":
            return "127.0.0.1"
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("daemon.host must be an IPv4 loopback address") from exc
        # The daemon pre-bind, doctor probe and current hook transport are IPv4. Accepting
        # ::1 here would look secure but fail later with an address-family error.
        if not isinstance(address, ipaddress.IPv4Address) or not address.is_loopback:
            raise ValueError("daemon.host must be an IPv4 loopback address")
        return host

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("daemon.port must be between 1 and 65535")
        return value

    @property
    def base_url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"


class IndexSettings(BaseModel):
    max_file_bytes: int = Field(1_500_000, gt=0)
    max_files: int = Field(200_000, gt=0)
    exclude_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
            "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
            "dist", "build", "target", ".next", ".nuxt", "out", "coverage",
            ".terraform", ".gradle", "vendor", ".idea", ".vscode", *names.variants(".truthstone"),
            ".tox", "site-packages", ".eggs", "htmlcov",
        ]
    )


class RetentionSettings(BaseModel):
    """How long each kind of data lives (Memory plan §5).

    Configuration values rather than hard-coded rules, as the plan requires. `0` means
    "keep indefinitely" — used for the two things that are worth keeping: validated
    project memory, and violations worth learning from.
    """

    raw_events_days: int = Field(14, ge=0)  # highest volume, lowest long-term value
    decisions_days: int = Field(30, ge=0)
    verifications_days: int = Field(60, ge=0)
    session_summaries_days: int = Field(270, ge=0)
    violations_days: int = Field(0, ge=0)  # long-term
    memories_days: int = Field(0, ge=0)  # long-term
    metrics_days: int = Field(90, ge=0)

    # Maintenance is deliberately infrequent and never runs while the agent is working.
    maintenance_interval_hours: float = Field(6.0, ge=0)
    vacuum_threshold_mb: float = Field(256.0, ge=0)


class DiskSettings(BaseModel):
    """Disk-space protection (Memory plan §8).

    The critical rule: "If SQLite fails or disk space becomes unavailable, Truthstone's
    core reliability functionality must continue working." Below `critical_free_mb` the
    store stops writing entirely — evidence checks, challenges and verification carry on,
    because none of them depend on being able to persist a log line.
    """

    low_free_mb: float = Field(1024.0, ge=0)  # prune aggressively below this
    critical_free_mb: float = Field(256.0, ge=0)  # stop writing below this
    max_database_mb: float = Field(512.0, ge=0)


class ChallengeSettings(BaseModel):
    """Anti-nag governance (SPEC §17, §39).

    Truthstone must not become "AI that constantly interrupts AI", so challenges are
    rationed: each distinct concern is raised at most once, and there is a hard ceiling
    per task after which Truthstone defers to the host and the human.
    """

    max_per_task: int = Field(6, ge=0)
    max_per_fingerprint: int = Field(1, ge=0)
    max_stop_blocks_per_task: int = Field(2, ge=0)
    # Below this severity nothing is ever surfaced to the agent.
    min_severity: str = "medium"
    # The original-tests check at Stop (``validate/original_tests.py``): existing tests the task
    # rewrote are run as they were, in a sandboxed copy, and an assertion failure for inputs the
    # request never mentions holds the "done". It runs repository code, and a request that changes
    # behaviour in prose (a limit, a unit, an error turned into a value) names none of the inputs
    # its updated tests use, so it is off until that is settled.
    original_tests: bool = False

    @field_validator("min_severity")
    @classmethod
    def valid_min_severity(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError("challenge.min_severity must be info, low, medium, high, or critical")
        return normalized


class NotesSettings(BaseModel):
    """Context Truthstone may add on its own initiative (M9, silence by default).

    The planning note (complexity, grounding, a proportional approach) went with every
    prompt. Its value for current agents is unmeasured and its misfires are recorded (it
    pointed agents at the protected tests and flagged the method they were asked to build),
    so it is off unless turned on here. The minimal profile (`core/profile.py`) still decides
    what reaches the agent; this only lets the planning note be one of those things.
    """

    planning: bool = False
    # The integrity note (``planning/integrity.py``): once per session, what "done" may not be
    # built on and the honest way out. Off until its effect on ordinary work is measured.
    integrity: bool = False


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Keys that used to exist. Reported like any unknown key, with the reason it is ignored.
_RETIRED_KEYS = {
    "latency": "removed: nothing ever enforced it (hook timeouts are written into the hook "
    "configuration by `truthstone install`)",
}


class Settings(BaseModel):
    enabled: bool = True
    # Phase 7's census switch. Every engine still runs and every finding is still
    # recorded; the agent hears none of it (see `core/observe.py`). Off by default —
    # while it is on, Truthstone provides no protection at all.
    observe_only: bool = False
    # What may reach the agent (core/profile.py, verify/arbiter.py): "minimal" lets only the
    # sanctioned interventions speak and records everything else; "full" lets every check speak.
    # TRUTHSTONE_PROFILE overrides it (`profile_override`), here and in `load`.
    profile: Literal["minimal", "full"] = Field(default_factory=lambda: profile_override() or "minimal")
    # Level for Truthstone's own loggers ("truthstone.*"), applied by `configure_logging`
    # in the daemon, whose stderr is daemon.log. WARNING is what was effectively
    # printed before the setting did anything; DEBUG adds e.g. missing-grammar notes.
    log_level: str = "WARNING"
    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    challenge: ChallengeSettings = Field(default_factory=ChallengeSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    disk: DiskSettings = Field(default_factory=DiskSettings)
    notes: NotesSettings = Field(default_factory=NotesSettings)
    _config_warnings: list[str] = PrivateAttr(default_factory=list)
    _unknown_keys: list[str] = PrivateAttr(default_factory=list)
    _daemon_config_error: str | None = PrivateAttr(default=None)

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        level = "WARNING" if level == "WARN" else level
        if level not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {', '.join(_LOG_LEVELS)}")
        return level

    @property
    def config_warning(self) -> str | None:
        """A non-fatal config load problem, for diagnostics such as ``doctor``."""
        if not self._config_warnings:
            return None
        more = len(self._config_warnings) - 1
        return self._config_warnings[0] + (f" (and {more} more)" if more else "")

    @property
    def config_warnings(self) -> list[str]:
        """One entry per rejected value or unreadable file; each says what was used instead."""
        return list(self._config_warnings)

    @property
    def unknown_keys(self) -> list[str]:
        """Dotted keys in config.toml that no setting reads (typos, retired settings)."""
        return list(self._unknown_keys)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        """Read config.toml. Never raises, and never discards more than it must.

        A rejected value falls back to its own default and is reported; every other
        value in the file still applies. (One bad value used to discard the whole file,
        so `max_per_task = -1` silently moved a configured port back to 8787, away from
        the port the installed hooks point at.)
        """
        path = path or (truthstone_home() / "config.toml")
        data: dict[str, Any] = {}
        warnings: list[str] = []
        unreadable_daemon = False
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                warnings.append(f"could not read {path}: {exc}; using built-in defaults")
                raw = None
            if raw is not None:
                try:
                    data = tomllib.loads(raw)
                except tomllib.TOMLDecodeError as exc:
                    # A broken config must never stop the agent from working.
                    warnings.append(f"could not parse {path}: {exc}; using built-in defaults")
                    unreadable_daemon = bool(_DAEMON_MENTION.search(raw))
        settings, invalid, rejections = cls._validate_leniently(data, path)
        settings._config_warnings = warnings + rejections
        settings._unknown_keys = _unknown_keys(cls, data)
        daemon_invalid = [key for key in invalid if key == "daemon" or key.startswith("daemon.")]
        if daemon_invalid:
            settings._daemon_config_error = (
                f"{', '.join(daemon_invalid)} in {path} is invalid; refusing to start the daemon on a "
                f"default endpoint the installed hooks may not point at. Fix [daemon] in {path}, "
                "then re-run `truthstone install claude` if the port changed."
            )
        elif unreadable_daemon:
            settings._daemon_config_error = (
                f"{path} cannot be parsed and it configures [daemon]; refusing to start the daemon on "
                f"a guessed endpoint. Fix {path} first."
            )
        if is_globally_disabled():
            settings.enabled = False
        if is_observe_only():
            settings.observe_only = True
        override = profile_override()
        if override is not None:
            settings.profile = override
        return settings

    @classmethod
    def _validate_leniently(cls, data: dict[str, Any], path: Path) -> tuple[Settings, list[str], list[str]]:
        """Validate, dropping each rejected value so its default applies. Returns
        (settings, rejected dotted keys, one warning per rejected key)."""
        data = copy.deepcopy(data)
        defaults = cls()
        invalid: list[str] = []
        warnings: list[str] = []
        for _ in range(64):  # each round drops at least one key; a config has few
            try:
                return cls.model_validate(data), invalid, warnings
            except ValidationError as exc:
                dropped = False
                for error in exc.errors():
                    key = _field_path(error.get("loc", ()))
                    if not key or not _drop(data, key):
                        continue
                    dropped = True
                    dotted = ".".join(key)
                    invalid.append(dotted)
                    default = _default_at(defaults, key)
                    shown = "its defaults" if isinstance(default, BaseModel) else f"the default {default!r}"
                    warnings.append(
                        f"{dotted} = {_short_repr(error.get('input'))} in {path} is invalid "
                        f"({error.get('msg', 'validation failed')}); using {shown}"
                    )
                if not dropped:
                    break
        # Unreachable for the current model (every field has a default); kept so a
        # future model-level validator can never turn a bad file into a crash.
        warnings.append(f"invalid configuration in {path}; using built-in defaults")
        return cls(), ["*"], warnings


# `[daemon]`, `daemon.port = …` or `daemon = {…}` in a file too broken to parse.
_DAEMON_MENTION = re.compile(r"(?m)^\s*(\[\s*daemon\s*\]|daemon\s*[.=])")


def _field_path(loc: tuple[Any, ...]) -> tuple[str, ...]:
    """The setting a validation error belongs to: its location up to any list index."""
    path: list[str] = []
    for part in loc:
        if not isinstance(part, str):
            break
        path.append(part)
    return tuple(path)


def _drop(data: dict[str, Any], key: tuple[str, ...]) -> bool:
    node: Any = data
    for part in key[:-1]:
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, dict) and key[-1] in node:
        del node[key[-1]]
        return True
    return False


def _default_at(settings: BaseModel, key: tuple[str, ...]) -> Any:
    value: Any = settings
    for part in key:
        value = getattr(value, part, None)
    return value


def _short_repr(value: Any, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _model_fields(model: type[BaseModel]) -> dict[str, type[BaseModel] | None]:
    """Field name -> nested settings model (or None for a plain value)."""
    out: dict[str, type[BaseModel] | None] = {}
    for name, field in model.model_fields.items():
        annotation = field.annotation
        nested = annotation if isinstance(annotation, type) and issubclass(annotation, BaseModel) else None
        out[name] = nested
    return out


def _unknown_keys(model: type[BaseModel], data: Any, prefix: str = "") -> list[str]:
    if not isinstance(data, dict):
        return []
    fields = _model_fields(model)
    unknown: list[str] = []
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if key not in fields:
            if isinstance(value, dict) and value:
                unknown.extend(f"{dotted}.{inner}" for inner in value)
            else:
                unknown.append(dotted)
            continue
        nested = fields[key]
        if nested is not None:
            unknown.extend(_unknown_keys(nested, value, f"{dotted}."))
    return unknown


def describe_unknown_key(key: str) -> str:
    """Why an unknown key is ignored, with a "did you mean" for a near miss."""
    parts = key.split(".")
    if parts[0] in _RETIRED_KEYS:
        return f"{key} is ignored: {_RETIRED_KEYS[parts[0]]}"
    model: type[BaseModel] | None = Settings
    for depth, part in enumerate(parts):
        fields = _model_fields(model) if model is not None else {}
        if part not in fields:
            guess = difflib.get_close_matches(part, list(fields), n=1, cutoff=0.6)
            if guess:
                return f"{key} is ignored (did you mean {'.'.join([*parts[:depth], guess[0]])}?)"
            return f"{key} is ignored (no such setting)"
        model = fields[part]
    return f"{key} is ignored"


def daemon_config_error(settings: Settings | None = None) -> str | None:
    """Why the daemon must not start on the configured endpoint, or ``None``.

    The hook URL is baked into the host's settings at install time. If `[daemon]` in
    config.toml is invalid (or unreadable), falling back to 127.0.0.1:8787 would bind a
    port the installed hooks may not point at, and every hook would fail open in
    silence. The daemon should refuse with this message instead (R11); `doctor` reports
    it, and `install` refuses to bake a guessed URL into the hooks.
    """
    settings = settings if settings is not None else Settings.load()
    return settings._daemon_config_error


# The name of the handler `configure_logging` adds when nothing else is configured.
DEFAULT_LOG_HANDLER = "truthstone-default"


def configure_logging(settings: Settings | None = None) -> None:
    """Apply ``log_level`` to the ``truthstone`` loggers of this process.

    Meant for the daemon (its stderr is daemon.log). Adds a stderr handler only when
    nothing in the process has configured logging, so an embedding application's
    handlers are left alone. The daemon installs its own redacting handler first
    (``daemon/logs.py``), which replaces this one if it was added earlier.
    """
    settings = settings if settings is not None else Settings.load()
    logger = logging.getLogger("truthstone")
    logger.setLevel(getattr(logging, settings.log_level, logging.WARNING))
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.set_name(DEFAULT_LOG_HANDLER)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)

