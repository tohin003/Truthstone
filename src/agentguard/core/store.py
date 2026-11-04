"""Persistence (SPEC §30 · Memory & Database Management Plan).

One SQLite database for every project, logically separated by project and session:

    AgentGuard SQLite
    ├── Projects
    │   ├── Project A -> Session 1, Session 2, ...
    │   └── Project B -> Session 1, ...
    └── Global configuration

Three properties this module is responsible for.

**Project isolation is structural.** The engine never holds the `Database`; it holds a
`ProjectStore` bound to one project, and there is no method on it that can express a
cross-project query. The memory plan's §4 — "AgentGuard must never accidentally use
Project A's architectural knowledge while working on Project B" — is therefore enforced by
the type, not by remembering to add a `WHERE`.

**Rows are bounded.** Per §6, a decision record holds the task, the verdict, evidence
*references* and a short summary — never a copy of the payload. Source code lives on disk
and in git; this database stores metadata and memory.

**Storage is never a dependency.** Per §8: "If SQLite fails or disk space becomes
unavailable, AgentGuard's core reliability functionality must continue working." Every
public method is wrapped so a failure returns a neutral value, and when free disk falls
below the critical threshold the store stops writing altogether. Evidence checks,
challenges and verification do not need to persist anything in order to work.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

from agentguard.core.config import (
    DiskSettings,
    RetentionSettings,
    Settings,
    database_path,
    ensure_private_dir,
)
from agentguard.core.events import AgentEvent
from agentguard.core.models import Decision
from agentguard.repo.gitinfo import repository_root

log = logging.getLogger(__name__)

SCHEMA_VERSION = 3

# Per §6: cap what a single row can hold. A tool argument blob is evidence that an action
# happened, not a place to archive file contents.
MAX_ARGUMENT_BYTES = 4_000
MAX_TEXT_BYTES = 2_000

# How long a statement waits for another connection's write lock (R7). On the hook hot
# path a busy database must cost a dropped row, never a missed deadline: a hook has 5 s,
# and SQLite's own 3 s wait per write was enough to blow it (the first event under an
# external lock took 6.3 s). Opening, migrating and maintaining the database happen off
# the hot path and can afford to wait for a concurrent maintenance pass or CLI command.
HOT_BUSY_TIMEOUT_MS = 100
MAINTENANCE_BUSY_TIMEOUT_MS = 3_000

# Failure logging is rate-limited per (operation, error type): under a held lock every
# write fails, and a traceback per event once filled the daemon log with 465 lines in
# seconds. Every failure is still counted (`Database.failure_count`, `stats()`).
_FAILURE_LOG_INTERVAL_S = 60.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    root       TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    git_remote TEXT NOT NULL DEFAULT '',
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL
);

-- Keyed on (id, project_id), not id alone. A session id is unique to the agent that
-- issued it, not to this database, so a bare `id` primary key means the *second* project
-- to report a given session id silently loses the row — and the census counts sessions.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT NOT NULL,
    project_id TEXT NOT NULL,
    agent      TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL,
    meta       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    prompt      TEXT NOT NULL DEFAULT '',
    spec        TEXT NOT NULL DEFAULT '{}',
    complexity  REAL,
    depth       TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  REAL NOT NULL,
    closed_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(project_id, session_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_retention
    ON tasks(project_id, status, closed_at, created_at);

CREATE TABLE IF NOT EXISTS events (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    task_id    TEXT,
    type       TEXT NOT NULL,
    agent      TEXT NOT NULL DEFAULT '',
    tool       TEXT,
    arguments  TEXT NOT NULL DEFAULT '{}',
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(project_id, task_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS decisions (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    event_id   TEXT NOT NULL DEFAULT '',
    task_id    TEXT,
    session_id TEXT NOT NULL DEFAULT '',
    tool       TEXT,
    action     TEXT NOT NULL,
    -- In observe-only mode `action` is always 'allow'; `would_have` is what AgentGuard
    -- would have done. Empty outside observe-only mode.
    would_have TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    level      INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_task ON decisions(project_id, task_id);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(project_id, ts);

CREATE TABLE IF NOT EXISTS findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    task_id     TEXT,
    category    TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    -- Which SPEC §3 failure mode this finding is evidence of. The census counts this
    -- column; inferring it from (category, verdict) at report time would make the
    -- taxonomy a guess made after the fact rather than a claim the detector made.
    failure_mode TEXT NOT NULL DEFAULT '',
    severity    TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '',
    evidence    TEXT NOT NULL DEFAULT '[]',
    fingerprint TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_decision ON findings(project_id, decision_id);
CREATE INDEX IF NOT EXISTS idx_findings_fp ON findings(project_id, task_id, fingerprint);

CREATE TABLE IF NOT EXISTS challenges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    times       INTEGER NOT NULL DEFAULT 1,
    resolved    INTEGER NOT NULL DEFAULT 0,
    first_ts    REAL NOT NULL,
    last_ts     REAL NOT NULL,
    UNIQUE(project_id, task_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_challenges_last_ts ON challenges(project_id, last_ts);

CREATE TABLE IF NOT EXISTS verifications (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '{}',
    started_at  REAL NOT NULL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_verifications_task ON verifications(project_id, task_id);

CREATE TABLE IF NOT EXISTS metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    value      REAL NOT NULL,
    labels     TEXT NOT NULL DEFAULT '{}',
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(project_id, name, ts);

-- Persistent project memory (Memory plan §3 · ACT II "memory confidence").
-- Created here so that violations and verification results are recorded from Phase 4
-- onward in a shape that can be promoted in Phase 9 without a migration. Nothing writes
-- to it yet: the plan is explicit that only *validated* knowledge is promoted, and
-- deciding what qualifies is Phase 9's job.
CREATE TABLE IF NOT EXISTS memories (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL,
    memory_type       TEXT NOT NULL,
    content           TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT '',
    source_files      TEXT NOT NULL DEFAULT '[]',
    confidence        REAL NOT NULL DEFAULT 0.5,
    validation_status TEXT NOT NULL DEFAULT 'unverified',
    session_id        TEXT NOT NULL DEFAULT '',
    created_at        REAL NOT NULL,
    last_verified     REAL
);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(project_id, validation_status);
"""


# -- project identity -------------------------------------------------------------


@dataclass(slots=True)
class ProjectIdentity:
    id: str
    root: str
    name: str
    git_remote: str


def _git_remote(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""


_SCP_REMOTE = re.compile(r"^(?P<user>[^/@:]+)@(?P<host>[^/:]+):(?P<path>.+)$")


def sanitize_git_remote(remote: str) -> str:
    """Return a stable remote identity without embedded credentials.

    Git accepts URLs such as ``https://user:token@example.com/org/repo.git`` and
    scp-style remotes such as ``git@example.com:org/repo.git``.  The former can leak a
    password/token into the shared database; the latter's transport username is not
    useful identity and makes SSH/HTTPS checkouts look different.  Strip userinfo,
    query strings and fragments while retaining host, optional port and repository path.
    """
    raw = remote.strip()
    if not raw:
        return ""

    match = _SCP_REMOTE.match(raw)
    if match:
        return f"{match.group('host')}:{match.group('path')}"

    try:
        parsed = urlsplit(raw)
        if parsed.scheme and parsed.hostname:
            hostname = parsed.hostname
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            try:
                port = f":{parsed.port}" if parsed.port is not None else ""
            except ValueError:
                port = ""
            return urlunsplit((parsed.scheme.lower(), f"{hostname}{port}", parsed.path, "", ""))
    except ValueError:
        pass

    # A malformed/unusual remote is still safer with obvious userinfo removed than
    # persisted verbatim.  Keep the original only when there is no credential marker.
    if "@" in raw:
        return raw.rsplit("@", 1)[-1]
    return raw


def project_identity(root: str | Path) -> ProjectIdentity:
    """Stable identity for a repository.

    The git remote is preferred over the path: a project moved, re-cloned or checked out
    as a worktree is still the same project, and its accumulated memory should follow it.
    Falls back to the canonical path outside git.
    """
    resolved = repository_root(root)
    remote = sanitize_git_remote(_git_remote(resolved))
    basis = remote or str(resolved)
    return ProjectIdentity(
        id=hashlib.sha256(basis.encode()).hexdigest()[:16],
        root=str(resolved),
        name=resolved.name,
        git_remote=remote,
    )


# -- bounded serialisation --------------------------------------------------------


def summarize_value(value: Any) -> Any:
    """Per §6: keep the shape, drop the bulk."""
    if isinstance(value, str):
        if len(value) <= 200:
            return value
        return f"{value[:200]}… <{len(value)} chars>"
    if isinstance(value, dict):
        return {k: summarize_value(v) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        head = [summarize_value(v) for v in value[:10]]
        return [*head, f"… <{len(value)} items>"] if len(value) > 10 else head
    return value


def summarize_arguments(arguments: dict[str, Any]) -> str:
    try:
        text = json.dumps(summarize_value(arguments), default=str)
    except (TypeError, ValueError):
        return "{}"
    return text[:MAX_ARGUMENT_BYTES]


def _safe(default: Any = None):
    """Storage must never break the agent. Roll back, report, carry on (Memory plan §8).

    The rollback is the important part (R7). A statement that fails part-way — most often
    "database is locked" because another process held the write lock — can leave the
    shared connection inside a transaction. The next read then pins a WAL snapshot, and
    once the other writer commits, every later write on this connection fails with
    SQLITE_BUSY_SNAPSHOT, forever: no task, no challenge, nothing persisted until the
    daemon restarts.
    """

    def deco(fn):
        def wrapper(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except Exception as exc:
                db = self if isinstance(self, Database) else getattr(self, "db", None)
                if isinstance(db, Database):
                    db._after_error(fn.__name__, exc)
                else:
                    log.exception("agentguard store: %s failed", fn.__name__)
                return default() if callable(default) else default

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return deco


def _is_busy(exc: BaseException) -> bool:
    """SQLITE_BUSY/LOCKED in any of its forms: another connection holds a lock."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    name = getattr(exc, "sqlite_errorname", "") or ""
    return name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED")) or "locked" in str(exc)


def _describe_error(exc: BaseException) -> str:
    """Type plus SQLite's own message. Never the statement's parameters (R17)."""
    if isinstance(exc, sqlite3.Error):
        name = getattr(exc, "sqlite_errorname", "") or ""
        return f"{type(exc).__name__}{f' ({name})' if name else ''}: {exc}"
    return type(exc).__name__


class Transaction:
    """The handle `Database.transaction()` yields. Its `execute` never raises.

    The first failing statement marks the whole transaction failed: later statements are
    skipped and the transaction is rolled back on exit, so a caller gets all of its rows
    or none of them. `committed` is the outcome; for a nested transaction it means
    "folded into the enclosing one", which is durable only once that one commits.
    """

    __slots__ = ("_conn", "active", "committed", "error")

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self.active = False
        self.committed = False
        self.error: BaseException | None = None

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor | None:
        if not self.active or self._conn is None:
            return None
        try:
            return self._conn.execute(sql, params)
        except sqlite3.Error as exc:
            self.fail(exc)
            return None

    def fail(self, exc: BaseException) -> None:
        if self.error is None:
            self.error = exc
        self.active = False


# -- the database -----------------------------------------------------------------


class Database:
    """The single shared connection, schema, maintenance and disk protection."""

    _instances: ClassVar[dict[str, Database]] = {}
    _registry_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: Path, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        self.path = path
        self.retention: RetentionSettings = settings.retention
        self.disk: DiskSettings = settings.disk
        self._lock = threading.RLock()
        self._last_maintenance = 0.0
        self._writes_disabled = False
        # Depth of `transaction()` contexts open on this connection. Only ever changed
        # while `_lock` is held, and a transaction holds `_lock` for its whole body.
        self._tx_depth = 0
        # Failures are counted, not just logged: "fail open, but never silently".
        self.failure_count = 0
        self.last_failure = ""
        self._failure_lock = threading.Lock()
        self._failure_logged: dict[tuple[str, str], float] = {}
        self._failures_unlogged = 0

        if path.is_symlink():
            raise RuntimeError(f"refusing to use symlink as database: {path}")
        if path.exists() and not path.is_file():
            raise RuntimeError(f"refusing to use non-regular database path: {path}")
        ensure_private_dir(self.path.parent)
        # `isolation_level=None`: no implicit BEGIN. A single write is its own atomic
        # statement, multi-statement writes go through `transaction()` (BEGIN IMMEDIATE),
        # and a read can never be left holding a snapshot inside a forgotten transaction.
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # Patient while opening and migrating; hot-path statements get the short wait.
        self._conn.execute(f"PRAGMA busy_timeout={MAINTENANCE_BUSY_TIMEOUT_MS}")
        # Before journal_mode: switching to WAL writes the header, after which SQLite
        # silently ignores an auto_vacuum change, and `incremental_vacuum` is a no-op.
        self._conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._harden_file_modes()
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._sanitize_project_remotes()
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._harden_file_modes()
            self._conn.execute(f"PRAGMA busy_timeout={HOT_BUSY_TIMEOUT_MS}")

    def _harden_file_modes(self) -> None:
        """Keep SQLite and its WAL sidecars owner-readable only.

        SQLite creates the database with the process umask, which is commonly ``022``.
        The database contains prompts, tool arguments and repository metadata, so relying
        on the caller's umask would make a normal installation world-readable.
        """
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                os.chmod(candidate, 0o600)

    # -- migration ----------------------------------------------------------------

    # Columns added after a table first shipped. `CREATE TABLE IF NOT EXISTS` is a no-op
    # on an existing table, so a new column has to be added explicitly or every database
    # created before this release keeps the old shape and every insert fails.
    #
    # Additive only, on purpose. A developer's decision history is not worth risking to a
    # rename, and every column here has a default that makes old rows readable: an empty
    # `failure_mode` means "recorded before the census existed", which is the truth.
    _ADDED_COLUMNS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        ("findings", "failure_mode", "TEXT NOT NULL DEFAULT ''"),
        ("decisions", "would_have", "TEXT NOT NULL DEFAULT ''"),
    )

    def _migrate(self) -> None:
        """Bring an existing database up to `SCHEMA_VERSION`. Never destructive."""
        for table, column, declaration in self._ADDED_COLUMNS:
            existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table absent entirely; the schema script just created it
            if column not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        self._rekey_sessions()

    def _sanitize_project_remotes(self) -> None:
        """Remove credentials from project identities written by older releases."""
        rows = self._conn.execute("SELECT id, git_remote FROM projects WHERE git_remote <> ''").fetchall()
        for row in rows:
            clean = sanitize_git_remote(str(row["git_remote"]))
            if clean != row["git_remote"]:
                self._conn.execute("UPDATE projects SET git_remote=? WHERE id=?", (clean, row["id"]))

    def _rekey_sessions(self) -> None:
        """Widen the sessions primary key from `id` to `(id, project_id)`.

        The only non-additive migration here, and it fixes a real defect: with `id` alone
        as the key, the second project to report a given session id had its row dropped by
        `INSERT OR IGNORE` and vanished from every count. Unlikely in production (agents
        issue UUIDs) but not impossible, and the census divides by this number.

        Copy-and-rename rather than an ALTER, because SQLite cannot change a primary key
        in place. The whole rebuild is one transaction, so a failure leaves the old table
        exactly as it was: an over-strict key under-counts sessions, while a half-finished
        rebuild loses them, so the old shape is strictly the safer place to stop.
        """
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchone()
        if row is None or "PRIMARY KEY (id, project_id)" in (row["sql"] or ""):
            return

        try:
            # One script, one transaction: `executescript` would commit an enclosing
            # transaction first, so the BEGIN has to live inside the script.
            self._conn.executescript(
                "BEGIN IMMEDIATE;\n"
                "ALTER TABLE sessions RENAME TO sessions_legacy;\n"
                f"{_SCHEMA}\n"
                "INSERT OR IGNORE INTO sessions(id, project_id, agent, started_at, ended_at, meta) "
                "SELECT id, project_id, agent, started_at, ended_at, meta FROM sessions_legacy;\n"
                "DROP TABLE sessions_legacy;\n"
                # The renamed table took the index name with it; recreate it on the new one.
                "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at);\n"
                "COMMIT;\n"
            )
        except sqlite3.Error:
            log.exception("agentguard store: sessions re-key failed; keeping the old table")
            with contextlib.suppress(sqlite3.Error):
                if self._conn.in_transaction:
                    self._conn.rollback()

    @classmethod
    def shared(cls, settings: Settings | None = None) -> Database:
        path = database_path()
        key = str(path)
        with cls._registry_lock:
            existing = cls._instances.get(key)
            if existing is None:
                existing = cls(path, settings)
                cls._instances[key] = existing
            return existing

    @classmethod
    def reset_shared(cls) -> None:
        """Drop cached handles — used by tests that relocate AGENTGUARD_HOME."""
        with cls._registry_lock:
            for instance in cls._instances.values():
                with contextlib.suppress(Exception):
                    instance.close()
            cls._instances.clear()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- failure handling (R7) ----------------------------------------------------

    def _rollback_quietly(self) -> None:
        """End whatever transaction a failed statement left open on the shared connection.

        Skipped while a `transaction()` context is open on this thread: that context owns
        the transaction and rolls it back itself. Another thread's context cannot be open
        here, because a transaction holds `_lock` for its whole body.
        """
        with self._lock:
            if self._tx_depth:
                return
            with contextlib.suppress(sqlite3.Error):
                if self._conn.in_transaction:
                    self._conn.rollback()

    def _after_error(self, where: str, exc: BaseException) -> None:
        self._rollback_quietly()
        self._note_failure(where, exc)

    def _note_failure(self, where: str, exc: BaseException) -> None:
        """Count every failure; log the first of each kind per interval."""
        now = time.monotonic()
        key = (where, type(exc).__name__)
        with self._failure_lock:
            self.failure_count += 1
            self.last_failure = f"{where}: {_describe_error(exc)}"
            last = self._failure_logged.get(key)
            if last is not None and now - last < _FAILURE_LOG_INTERVAL_S:
                self._failures_unlogged += 1
                return
            self._failure_logged[key] = now
            unlogged, self._failures_unlogged = self._failures_unlogged, 0
        more = f" ({unlogged} more failure(s) since the last report)" if unlogged else ""
        if _is_busy(exc):
            log.warning(
                "agentguard store: %s dropped: the database is busy (another process holds "
                "its write lock); guarding continues without persistence%s",
                where,
                more,
            )
        elif isinstance(exc, sqlite3.Error):
            log.warning("agentguard store: %s failed: %s%s", where, _describe_error(exc), more)
        else:
            # Not a storage condition but a defect: keep the traceback.
            log.error("agentguard store: %s failed%s", where, more, exc_info=exc)

    # -- disk protection ----------------------------------------------------------

    def free_megabytes(self) -> float:
        try:
            return shutil.disk_usage(self.path.parent).free / (1024 * 1024)
        except OSError:
            return float("inf")  # unknowable: do not degrade on a bad reading

    def disk_state(self) -> str:
        free = self.free_megabytes()
        if free < self.disk.critical_free_mb:
            return "critical"
        if free < self.disk.low_free_mb:
            return "low"
        return "healthy"

    @property
    def writes_enabled(self) -> bool:
        if self._writes_disabled:
            return False
        return self.disk_state() != "critical"

    @property
    def database_over_limit(self) -> bool:
        """Whether the configured database-size budget has been exceeded.

        ``max_database_mb`` is a maintenance budget, not a second fail-closed switch.
        Reaching it should trigger cleanup, but stopping all writes here would also stop
        the cleanup that could recover the database.  Critical *filesystem* pressure
        remains the only condition that disables writes (the reliability guarantee in
        §8).
        """
        limit = self.disk.max_database_mb
        return limit > 0 and self.size_megabytes() >= limit

    # -- primitives ---------------------------------------------------------------

    def write(self, sql: str, params: tuple) -> bool:
        """One statement, atomic on its own. Returns whether it ran.

        Raises on failure (callers are `_safe`), but only after rolling back, so the
        shared connection is never left inside a transaction. Inside an enclosing
        `transaction()` the statement simply joins it.
        """
        if not self.writes_enabled:
            return False  # §8: reliability continues without persistence
        with self._lock:
            try:
                self._conn.execute(sql, params)
            except sqlite3.Error:
                self._rollback_quietly()
                raise
        return True

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self._conn.execute(sql, params).fetchall()
            except sqlite3.Error:
                self._rollback_quietly()
                raise

    @contextlib.contextmanager
    def transaction(self, name: str = "transaction") -> Iterator[Transaction]:
        """``BEGIN IMMEDIATE … COMMIT`` around a group of writes. Never raises.

        * Every statement goes through the yielded `Transaction`; the first failure
          rolls the whole group back, and so does an exception from the body, which is
          logged and swallowed — storage must never break the hot path.
        * ``BEGIN IMMEDIATE`` takes the write lock up front. A busy database therefore
          fails at BEGIN, after at most the hot-path busy timeout, with nothing written;
          a deferred transaction would fail half-way instead.
        * Nest-safe: inside another transaction it becomes a SAVEPOINT, so an inner
          failure undoes only the inner work.
        * With writes disabled (critical disk) the body still runs and nothing is written.

        ``with db.transaction() as tx: tx.execute(...)`` then check ``tx.committed``.
        """
        tx = Transaction()
        with self._lock:
            conn = self._conn
            depth = self._tx_depth
            savepoint = f"agentguard_{depth}"
            began = False
            if self.writes_enabled:
                try:
                    conn.execute(f"SAVEPOINT {savepoint}" if depth else "BEGIN IMMEDIATE")
                except sqlite3.Error as exc:
                    tx.fail(exc)
                    self._rollback_quietly()
                else:
                    tx._conn = conn
                    tx.active = began = True
                    self._tx_depth += 1
            try:
                yield tx
            except Exception as exc:  # noqa: BLE001 - the hot path never sees storage errors
                tx.fail(exc)
            except BaseException:
                tx.active = False  # interrupted: roll back, then let it propagate
                raise
            finally:
                if began:
                    self._tx_depth -= 1
                    self._end_transaction(tx, conn, savepoint if depth else None)
        if tx.error is not None:
            self._note_failure(name, tx.error)

    @staticmethod
    def _end_transaction(tx: Transaction, conn: sqlite3.Connection, savepoint: str | None) -> None:
        if tx.active:
            try:
                conn.execute(f"RELEASE {savepoint}" if savepoint else "COMMIT")
            except sqlite3.Error as exc:
                tx.fail(exc)
            else:
                tx.active = False
                tx.committed = True
                return
        tx.active = False
        with contextlib.suppress(sqlite3.Error):
            if savepoint:
                conn.execute(f"ROLLBACK TO {savepoint}")
                conn.execute(f"RELEASE {savepoint}")
            elif conn.in_transaction:
                conn.rollback()

    @contextlib.contextmanager
    def _maintenance_window(self) -> Iterator[sqlite3.Connection]:
        """The connection, held, with the patient busy timeout; restored on exit.

        `busy_timeout` is per connection, so it is raised only while `_lock` keeps every
        hot-path statement out.
        """
        with self._lock:
            self._conn.execute(f"PRAGMA busy_timeout={MAINTENANCE_BUSY_TIMEOUT_MS}")
            try:
                yield self._conn
            finally:
                with contextlib.suppress(sqlite3.Error):
                    self._conn.execute(f"PRAGMA busy_timeout={HOT_BUSY_TIMEOUT_MS}")

    # -- maintenance (Memory plan §7) ---------------------------------------------

    def maintenance_due(self) -> bool:
        interval = self.retention.maintenance_interval_hours * 3600
        return self.database_over_limit or (time.time() - self._last_maintenance) >= interval

    @_safe(default=dict)
    def maintain(self, force: bool = False) -> dict[str, int]:
        """Prune expired rows, checkpoint the WAL, reclaim pages.

        Never call this on the hook hot path. It runs on `SessionEnd`, when the agent has
        finished and a hundred milliseconds costs nobody anything (§7: "Avoid running
        expensive maintenance during active agent execution").
        """
        if not force and not self.maintenance_due():
            return {}
        self._last_maintenance = time.time()

        aggressive = self.disk_state() != "healthy" or self.database_over_limit
        removed = self.prune(aggressive=aggressive)

        with self._maintenance_window() as conn:
            # Step it to completion: `incremental_vacuum` frees one page per row it
            # yields, so an execute() whose cursor is dropped reclaims a single page.
            conn.execute("PRAGMA incremental_vacuum").fetchall()
            # Checkpoint after the vacuum, so the pages it moved leave the WAL too.
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            self._harden_file_modes()

        if self.size_megabytes() > self.retention.vacuum_threshold_mb or self.database_over_limit:
            with self._maintenance_window() as conn:
                # A database created before auto_vacuum was set in the right order is
                # converted by the full VACUUM that is running anyway.
                conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
                conn.execute("VACUUM")
                self._harden_file_modes()
        return removed

    @_safe(default=dict)
    def prune(self, aggressive: bool = False) -> dict[str, int]:
        """Apply the retention tiers. `0` days means keep indefinitely."""
        scale = 0.25 if aggressive else 1.0
        rules = [
            ("events", self.retention.raw_events_days, "ts"),
            ("decisions", self.retention.decisions_days, "ts"),
            ("verifications", self.retention.verifications_days, "started_at"),
            ("metrics", self.retention.metrics_days, "ts"),
        ]
        removed: dict[str, int] = {}
        now = time.time()
        for table, days, column in rules:
            if days <= 0:
                continue
            cutoff = now - (days * scale * 86400)
            with self._maintenance_window() as conn:
                cursor = conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
                removed[table] = cursor.rowcount if cursor.rowcount > 0 else 0

        # Sessions are summaries, but an active session is not a summary yet. Keep it
        # (and its open task) even if a daemon happens to run maintenance after a long
        # uninterrupted session. A crashed session has no ended_at and is treated the
        # same way; this is safer than deleting the state that lets the next event fail
        # open without losing attribution.
        summary_days = self.retention.session_summaries_days
        if summary_days > 0:
            cutoff = now - (summary_days * scale * 86400)
            with self._maintenance_window() as conn:
                # One transaction for the pair; on failure `_safe` rolls it back.
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE started_at < ? AND ended_at IS NOT NULL",
                    (cutoff,),
                )
                removed["sessions"] = cursor.rowcount if cursor.rowcount > 0 else 0

                # Closed tasks are session-level summaries too. Also remove old tasks
                # whose session summary has already disappeared (or was never recorded
                # because persistence was unavailable). Open tasks survive unless their
                # session is definitively gone and the task itself is old.
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE "
                    "(status <> 'open' AND COALESCE(closed_at, created_at) < ?) OR "
                    "(status = 'open' AND created_at < ? AND NOT EXISTS ("
                    "  SELECT 1 FROM sessions s WHERE s.id=tasks.session_id "
                    "  AND s.project_id=tasks.project_id"
                    "))",
                    (cutoff, cutoff),
                )
                removed["tasks"] = cursor.rowcount if cursor.rowcount > 0 else 0
                conn.execute("COMMIT")
        else:
            # Keep the keys stable for callers (CLI/reporting) while honoring the
            # documented `0 means keep indefinitely` retention setting.
            removed["sessions"] = 0
            removed["tasks"] = 0

        # Challenges have no independent retention setting: they are useful only as
        # part of a task summary. Remove challenges attached to tasks deleted above and
        # orphan rows left by an interrupted write. A challenge without its task cannot
        # participate in rationing, so retaining it would only consume storage.
        removed["challenges"] = 0
        with self._maintenance_window() as conn:
            # Include project_id in the join: task ids are normally UUIDs, but callers
            # and older databases may contain human-readable ids reused across projects.
            # A bare `task_id NOT IN (...)` cleanup would violate project isolation.
            cursor = conn.execute(
                "DELETE FROM challenges WHERE NOT EXISTS ("
                "  SELECT 1 FROM tasks t WHERE t.id=challenges.task_id "
                "  AND t.project_id=challenges.project_id"
                ")"
            )
            removed["challenges"] += max(cursor.rowcount, 0)

        # Findings belong to decisions; a finding whose decision is gone is unreadable.
        # Violations worth keeping are promoted to `memories` in Phase 9.
        with self._maintenance_window() as conn:
            cursor = conn.execute(
                "DELETE FROM findings AS f WHERE NOT EXISTS ("
                "  SELECT 1 FROM decisions d WHERE d.id=f.decision_id "
                "  AND d.project_id=f.project_id"
                ")"
            )
            removed["findings"] = max(cursor.rowcount, 0)
        return removed

    def size_megabytes(self) -> float:
        try:
            # WAL mode keeps recent writes in sidecar files. Measuring only the main
            # database made `max_database_mb` appear ineffective precisely while the
            # WAL was carrying the bulk of the data.
            total = 0
            for suffix in ("", "-wal", "-shm"):
                with contextlib.suppress(OSError):
                    total += Path(f"{self.path}{suffix}").stat().st_size
            return total / (1024 * 1024)
        except OSError:
            return 0.0

    @_safe(default=dict)
    def stats(self) -> dict[str, Any]:
        tables = (
            "projects", "sessions", "tasks", "events", "decisions",
            "findings", "challenges", "verifications", "metrics", "memories",
        )
        counts = {
            table: int(self.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]) for table in tables
        }
        return {
            "path": str(self.path),
            "size_mb": round(self.size_megabytes(), 2),
            "free_disk_mb": round(self.free_megabytes(), 1),
            "disk_state": self.disk_state(),
            "writes_enabled": self.writes_enabled,
            "database_over_limit": self.database_over_limit,
            "max_database_mb": self.disk.max_database_mb,
            "rows": counts,
        }


# -- the project-scoped handle ----------------------------------------------------


class ProjectStore:
    """Everything the engine can do with storage, bound to one project.

    There is deliberately no method here that takes a project id. Cross-project access is
    not restricted — it is unrepresentable.
    """

    def __init__(self, db: Database, identity: ProjectIdentity) -> None:
        self.db = db
        self.identity = identity
        self.project_id = identity.id
        self._register()

    @classmethod
    def for_workspace(cls, workspace: str | Path, settings: Settings | None = None) -> ProjectStore:
        return cls(Database.shared(settings), project_identity(workspace))

    @_safe()
    def _register(self) -> None:
        now = time.time()
        self.db.write(
            "INSERT INTO projects(id, root, name, git_remote, first_seen, last_seen) "
            "VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, root=excluded.root",
            (self.project_id, self.identity.root, self.identity.name, self.identity.git_remote, now, now),
        )

    def close(self) -> None:
        """A project handle owns nothing; the database is shared and stays open."""

    # -- sessions -----------------------------------------------------------------

    @_safe()
    def open_session(
        self, session_id: str, agent: str, workspace: str = "", meta: dict | None = None
    ) -> None:
        if not session_id:
            return
        self.db.write(
            "INSERT OR IGNORE INTO sessions(id, project_id, agent, started_at, meta) VALUES(?,?,?,?,?)",
            (session_id, self.project_id, agent, time.time(), json.dumps(meta or {})[:MAX_TEXT_BYTES]),
        )

    @_safe()
    def close_session(self, session_id: str) -> None:
        ended_at = time.time()
        # Closing a session is the durable lifecycle boundary for its tasks. Without
        # this update every prompt-created task stayed `open` forever, so retention could
        # never reclaim task/challenge rows and `current_task_id()` kept seeing stale work
        # after a clean SessionEnd. Keep both writes in one transaction where possible;
        # the public wrapper still fails open if storage is unavailable.
        # An empty adapter session id is an unscoped event, not a session handle. Never
        # let SessionEnd for such a payload close every anonymous task in the project.
        if not session_id or not self.db.writes_enabled:
            return
        with self.db.transaction("close_session") as tx:
            tx.execute(
                "UPDATE sessions SET ended_at=? WHERE id=? AND project_id=?",
                (ended_at, session_id, self.project_id),
            )
            tx.execute(
                "UPDATE tasks SET status='closed', closed_at=? "
                "WHERE project_id=? AND session_id=? AND status='open'",
                (ended_at, self.project_id, session_id),
            )

    # -- tasks --------------------------------------------------------------------

    @_safe()
    def create_task(
        self,
        session_id: str,
        prompt: str,
        spec: dict | None = None,
        complexity: float | None = None,
        depth: str | None = None,
    ) -> str:
        if not session_id:
            return ""
        task_id = uuid.uuid4().hex
        self.db.write(
            "INSERT INTO tasks(id, project_id, session_id, prompt, spec, complexity, depth, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                task_id,
                self.project_id,
                session_id,
                prompt[:MAX_TEXT_BYTES],
                json.dumps(spec or {}, default=str)[:MAX_ARGUMENT_BYTES],
                complexity,
                depth,
                time.time(),
            ),
        )
        return task_id

    @_safe()
    def current_task_id(self, session_id: str) -> str | None:
        rows = self.db.query(
            "SELECT id FROM tasks WHERE project_id=? AND session_id=? AND status='open' "
            "ORDER BY created_at DESC LIMIT 1",
            (self.project_id, session_id),
        )
        return rows[0]["id"] if rows else None

    @_safe()
    def close_task(self, task_id: str, status: str = "closed") -> None:
        self.db.write(
            "UPDATE tasks SET status=?, closed_at=? WHERE id=? AND project_id=?",
            (status, time.time(), task_id, self.project_id),
        )

    # -- events & decisions -------------------------------------------------------

    _EVENT_SQL = (
        "INSERT OR REPLACE INTO events"
        "(id, project_id, session_id, task_id, type, agent, tool, arguments, ts) "
        "VALUES(?,?,?,?,?,?,?,?,?)"
    )
    _DECISION_SQL = (
        "INSERT OR REPLACE INTO decisions"
        "(id, project_id, event_id, task_id, session_id, tool, action, would_have, reason, "
        " level, latency_ms, ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    _FINDING_SQL = (
        "INSERT INTO findings"
        "(project_id, decision_id, task_id, category, verdict, failure_mode, severity, "
        " subject, summary, detail, evidence, fingerprint, ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )

    def _event_row(self, event: AgentEvent) -> tuple:
        return (
            event.event_id,
            self.project_id,
            event.session_id,
            event.task_id,
            str(event.event),
            event.agent,
            event.tool,
            summarize_arguments(event.arguments),
            event.ts,
        )

    def _decision_row(self, event: AgentEvent, decision: Decision, decision_id: str, now: float) -> tuple:
        return (
            decision_id,
            self.project_id,
            event.event_id,
            event.task_id,
            event.session_id,
            event.tool,
            str(decision.action),
            str(decision.would_have or ""),
            decision.reason[:MAX_TEXT_BYTES],
            int(decision.level),
            decision.latency_ms,
            now,
        )

    def _finding_rows(
        self, event: AgentEvent, decision: Decision, decision_id: str, now: float
    ) -> list[tuple]:
        return [
            (
                self.project_id,
                decision_id,
                event.task_id,
                str(f.category),
                str(f.verdict),
                str(f.failure_mode),
                str(f.severity),
                f.subject[:200],
                f.summary[:500],
                f.detail[:MAX_TEXT_BYTES],
                json.dumps([e.model_dump() for e in f.evidence], default=str)[:MAX_ARGUMENT_BYTES],
                f.fingerprint(),
                now,
            )
            for f in decision.findings
        ]

    @_safe()
    def record_event(self, event: AgentEvent) -> None:
        self.db.write(self._EVENT_SQL, self._event_row(event))

    @_safe(default="")
    def record_decision(self, event: AgentEvent, decision: Decision) -> str:
        decision_id = decision.decision_id or uuid.uuid4().hex
        now = time.time()
        self.db.write(self._DECISION_SQL, self._decision_row(event, decision, decision_id, now))
        for row in self._finding_rows(event, decision, decision_id, now):
            self.db.write(self._FINDING_SQL, row)
        return decision_id

    @_safe(default="")
    def record_event_and_decision(self, event: AgentEvent, decision: Decision) -> str:
        """The event, its decision and the decision's findings: one transaction (R7).

        Returns the decision id once all of it is committed, or ``""`` when nothing was
        persisted (busy database, writes disabled, any failure) — never a partial record,
        and never an exception. One commit per event instead of two or more also halves
        the WAL traffic on the hot path.
        """
        decision_id = decision.decision_id or uuid.uuid4().hex
        now = time.time()
        # Build every row before taking the write lock: serialising arguments and
        # evidence is the slow part, and the lock should be held for the inserts only.
        rows = [
            (self._EVENT_SQL, self._event_row(event)),
            (self._DECISION_SQL, self._decision_row(event, decision, decision_id, now)),
            *((self._FINDING_SQL, row) for row in self._finding_rows(event, decision, decision_id, now)),
        ]
        with self.db.transaction("record_event_and_decision") as tx:
            for sql, params in rows:
                tx.execute(sql, params)
        return decision_id if tx.committed else ""

    @_safe(default=list)
    def recent_decisions(self, limit: int = 50) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM decisions WHERE project_id=? ORDER BY ts DESC LIMIT ?",
            (self.project_id, limit),
        )
        return [dict(r) for r in rows]

    @_safe(default=None)
    def decision_detail(self, decision_id: str) -> dict | None:
        rows = self.db.query(
            "SELECT * FROM decisions WHERE id=? AND project_id=?", (decision_id, self.project_id)
        )
        if not rows:
            return None
        out = dict(rows[0])
        out["findings"] = [
            dict(r)
            for r in self.db.query(
                "SELECT * FROM findings WHERE decision_id=? AND project_id=?",
                (decision_id, self.project_id),
            )
        ]
        return out

    # -- failure-mode census (SPEC §3 · Phase 7) ----------------------------------

    @_safe(default=list)
    def failure_mode_counts(self, since: float) -> list[dict]:
        """Observations per SPEC §3 failure mode, since `since`.

        Two counts, because they answer different questions. `occurrences` is how often
        the detector fired; `tasks` is how many distinct pieces of work were affected.
        A single stubborn edit retried six times is six occurrences and one task, and
        reporting only the first would make one bad afternoon look like an epidemic.

        Rows with an empty `failure_mode` predate the census and are excluded — counting
        them as anything would be inventing data.
        """
        rows = self.db.query(
            "SELECT failure_mode, COUNT(*) AS occurrences, "
            "       COUNT(DISTINCT COALESCE(task_id, decision_id)) AS tasks, "
            "       COUNT(DISTINCT fingerprint) AS distinct_subjects, "
            "       MAX(ts) AS last_seen "
            "FROM findings WHERE project_id=? AND ts>? AND failure_mode NOT IN ('', ?) "
            "GROUP BY failure_mode ORDER BY occurrences DESC",
            (self.project_id, since, "not_a_failure"),
        )
        return [dict(r) for r in rows]

    @_safe(default=list)
    def failure_mode_examples(self, mode: str, since: float, limit: int = 3) -> list[dict]:
        """A few real observations of one mode, for the report's evidence column."""
        rows = self.db.query(
            "SELECT subject, summary, severity, ts FROM findings "
            "WHERE project_id=? AND ts>? AND failure_mode=? "
            "GROUP BY fingerprint ORDER BY ts DESC LIMIT ?",
            (self.project_id, since, mode, limit),
        )
        return [dict(r) for r in rows]

    @_safe(default=dict)
    def activity(self, since: float) -> dict[str, Any]:
        """The denominators. A count of failures without them is not a rate."""

        def scalar(sql: str, params: tuple) -> int:
            rows = self.db.query(sql, params)
            return int(rows[0][0]) if rows else 0

        pid = self.project_id
        sessions = scalar(
            "SELECT COUNT(*) FROM sessions WHERE project_id=? AND started_at>?", (pid, since)
        )
        observed_sessions = scalar(
            "SELECT COUNT(*) FROM sessions WHERE project_id=? AND started_at>? "
            "AND meta LIKE '%\"observe_only\": true%'",
            (pid, since),
        )
        return {
            "sessions": sessions,
            "observe_only_sessions": observed_sessions,
            "tasks": scalar(
                "SELECT COUNT(*) FROM tasks WHERE project_id=? AND created_at>?", (pid, since)
            ),
            "decisions": scalar(
                "SELECT COUNT(*) FROM decisions WHERE project_id=? AND ts>?", (pid, since)
            ),
            "would_have_spoken": scalar(
                "SELECT COUNT(*) FROM decisions WHERE project_id=? AND ts>? "
                "AND would_have NOT IN ('', 'allow')",
                (pid, since),
            ),
            "first_seen": (
                self.db.query(
                    "SELECT COALESCE(MIN(started_at), 0) FROM sessions "
                    "WHERE project_id=? AND started_at>?",
                    (pid, since),
                )[0][0]
            ),
        }

    # -- challenge ledger (SPEC §17, §39) -----------------------------------------

    @_safe(default=0)
    def challenge_count(self, task_id: str, fingerprint: str | None = None) -> int:
        if fingerprint is None:
            rows = self.db.query(
                "SELECT COALESCE(SUM(times), 0) AS n FROM challenges WHERE project_id=? AND task_id=?",
                (self.project_id, task_id),
            )
        else:
            rows = self.db.query(
                "SELECT COALESCE(SUM(times), 0) AS n FROM challenges "
                "WHERE project_id=? AND task_id=? AND fingerprint=?",
                (self.project_id, task_id, fingerprint),
            )
        return int(rows[0]["n"]) if rows else 0

    @_safe()
    def record_challenge(self, task_id: str, fingerprint: str, subject: str = "") -> None:
        now = time.time()
        self.db.write(
            "INSERT INTO challenges(project_id, task_id, fingerprint, subject, times, first_ts, last_ts) "
            "VALUES(?,?,?,?,1,?,?) "
            "ON CONFLICT(project_id, task_id, fingerprint) "
            "DO UPDATE SET times=times+1, last_ts=excluded.last_ts",
            (self.project_id, task_id, fingerprint, subject[:200], now, now),
        )

    @_safe()
    def resolve_challenge(self, task_id: str, fingerprint: str) -> None:
        self.db.write(
            "UPDATE challenges SET resolved=1 WHERE project_id=? AND task_id=? AND fingerprint=?",
            (self.project_id, task_id, fingerprint),
        )

    # -- verification -------------------------------------------------------------

    @_safe(default="")
    def start_verification(self, task_id: str, kind: str) -> str:
        vid = uuid.uuid4().hex
        self.db.write(
            "INSERT INTO verifications(id, project_id, task_id, kind, status, started_at) "
            "VALUES(?,?,?,?,?,?)",
            (vid, self.project_id, task_id, kind, "running", time.time()),
        )
        return vid

    @_safe()
    def finish_verification(self, verification_id: str, status: str, detail: dict | None = None) -> None:
        self.db.write(
            "UPDATE verifications SET status=?, detail=?, finished_at=? WHERE id=? AND project_id=?",
            (
                status,
                json.dumps(summarize_value(detail or {}), default=str)[:MAX_ARGUMENT_BYTES],
                time.time(),
                verification_id,
                self.project_id,
            ),
        )

    @_safe(default=list)
    def verifications_for(self, task_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self.db.query(
                "SELECT * FROM verifications WHERE project_id=? AND task_id=?",
                (self.project_id, task_id),
            )
        ]

    # -- metrics (SPEC §37) -------------------------------------------------------

    @_safe()
    def record_metric(self, name: str, value: float, labels: dict | None = None) -> None:
        self.db.write(
            "INSERT INTO metrics(project_id, name, value, labels, ts) VALUES(?,?,?,?,?)",
            (self.project_id, name, float(value), json.dumps(labels or {})[:500], time.time()),
        )

    @_safe(default=list)
    def metric_values(self, name: str, limit: int = 10_000) -> list[float]:
        rows = self.db.query(
            "SELECT value FROM metrics WHERE project_id=? AND name=? ORDER BY ts DESC LIMIT ?",
            (self.project_id, name, limit),
        )
        return [float(r["value"]) for r in rows]

    # -- persistent memory (written from Phase 9) ---------------------------------

    @_safe(default=list)
    def memories(self, memory_type: str | None = None, limit: int = 100) -> list[dict]:
        if memory_type:
            rows = self.db.query(
                "SELECT * FROM memories WHERE project_id=? AND memory_type=? "
                "ORDER BY confidence DESC LIMIT ?",
                (self.project_id, memory_type, limit),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM memories WHERE project_id=? ORDER BY confidence DESC LIMIT ?",
                (self.project_id, limit),
            )
        return [dict(r) for r in rows]

    @_safe(default="")
    def remember(
        self,
        memory_type: str,
        content: str,
        source: str = "",
        source_files: list[str] | None = None,
        confidence: float = 0.5,
        validation_status: str = "unverified",
        session_id: str = "",
    ) -> str:
        """Promote one validated fact into long-term project memory.

        Deliberately not called from anywhere yet. The memory plan is explicit that only
        useful, validated, project-specific knowledge is promoted — "Do not automatically
        save every agent response" — and deciding what qualifies is Phase 9's work.
        """
        memory_id = uuid.uuid4().hex
        self.db.write(
            "INSERT INTO memories(id, project_id, memory_type, content, source, source_files, "
            "confidence, validation_status, session_id, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                memory_id,
                self.project_id,
                memory_type,
                content[:MAX_TEXT_BYTES],
                source[:500],
                json.dumps(source_files or [])[:MAX_TEXT_BYTES],
                float(confidence),
                validation_status,
                session_id,
                time.time(),
            ),
        )
        return memory_id


# Backwards-compatible alias: the engine and CLI talk to a project-scoped handle.
Store = ProjectStore
