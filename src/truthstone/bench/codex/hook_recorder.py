"""The harness's logging hook, installed identically in both arms. Stdlib only.

The host runs it for every hook event with the payload on stdin. It appends one line per
event to ``$HOOK_TRACE_DIR/hooks.jsonl``:

* the **full payload** (``tool_input``, and on PostToolUse ``tool_response``: what the tool
  returned), long strings capped, so a cell can be replayed offline through any build
  (``truthstone.bench.replay``, pre-registration WP1(b));
* the **tree** the working directory held at that moment: ``git write-tree`` over a
  temporary index kept in the trace directory, with the objects written to
  ``$HOOK_TRACE_DIR/objects``. Nothing in the repository changes (not its index, not its
  object store), the first event hashes the whole tree and later ones only what changed,
  and the trace alone can rebuild the tree of every event;
* on ``Stop``, a copy of the working tree in ``$HOOK_TRACE_DIR/stop-<n>/``, so the grader can
  later ask whether the hidden tests passed at the very moment a completion gate held the
  turn (a *false block* if they did).

It never writes to stdout and always exits 0: anything else could change what the host
does, and exit code 2 would be read as "block".
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time

TRACE_ENV = "HOOK_TRACE_DIR"
SKIP = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
MAX_SNAPSHOT_FILES = 5000
MAX_STRING = 200_000  # characters kept of any one string in a payload
TREE_TIMEOUT_S = 4  # per git call; three calls stay inside the host's 15 s hook timeout


def _snapshot(cwd, dest):
    count = 0
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for name in filenames:
            count += 1
            if count > MAX_SNAPSHOT_FILES:
                return
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, cwd)
            target = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                shutil.copy2(src, target, follow_symlinks=False)
            except OSError:
                continue


def _capped(value):
    """The payload as sent, with any very long string cut (and marked as cut)."""
    if isinstance(value, str):
        return (
            value if len(value) <= MAX_STRING else value[:MAX_STRING] + f"\n<cut {len(value) - MAX_STRING}>"
        )
    if isinstance(value, dict):
        return {k: _capped(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_capped(v) for v in value]
    return value


def _tree(cwd, trace):
    """``git write-tree`` of the working directory, through the trace's own index and object
    store. Returns (tree id, None) or (None, why it could not)."""
    objects = os.path.join(trace, "objects")
    os.makedirs(objects, exist_ok=True)
    env = dict(os.environ)
    for name in [k for k in env if k.startswith("GIT_")]:
        env.pop(name)
    env.update(
        {
            "GIT_INDEX_FILE": os.path.join(trace, "tree.index"),
            "GIT_OBJECT_DIRECTORY": objects,
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TREE_TIMEOUT_S,
            check=False,
        )
        if top.returncode != 0:
            return None, f"not a git work tree: {top.stderr.strip()[-200:]}"
        root = top.stdout.strip()
        for argv in (["add", "--all", "--", "."], ["write-tree"]):
            proc = subprocess.run(
                ["git", "-C", root, *argv],
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TREE_TIMEOUT_S,
                check=False,
            )
            if proc.returncode != 0:
                return None, f"git {argv[0]}: {proc.stderr.strip()[-200:]}"
        return proc.stdout.strip(), None
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"[:200]


def main():
    trace = os.environ.get(TRACE_ENV)
    if not trace:
        return
    started = time.time()
    raw = sys.stdin.buffer.read(2_000_000)
    try:
        payload = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        payload = {"unparsable": True}
    if not isinstance(payload, dict):
        payload = {"unparsable": True}
    event = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
    record = {
        "ts": started,
        "event": event,
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
        "tool": payload.get("tool_name"),
        "tool_input": payload.get("tool_input"),
        "stop_hook_active": payload.get("stop_hook_active"),
        "last_assistant_message": (payload.get("last_assistant_message") or "")[:4000] or None,
        # Settings as the host reported them to its hooks: a per-cell check of the pins.
        "model": payload.get("model"),
        "effort": payload.get("effort"),
        "permission_mode": payload.get("permission_mode"),
        # The whole event as the host sent it, for offline replay.
        "payload": _capped(payload),
    }
    os.makedirs(trace, exist_ok=True)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and os.path.isdir(cwd):
        tree_started = time.time()
        record["tree"], error = _tree(cwd, trace)
        record["tree_ms"] = round((time.time() - tree_started) * 1000, 2)
        if error:
            record["tree_error"] = error
        if event == "Stop":
            existing = [d for d in os.listdir(trace) if d.startswith("stop-")]
            dest = os.path.join(trace, f"stop-{len(existing) + 1}")
            _snapshot(cwd, dest)
            record["snapshot"] = os.path.basename(dest)
    record["elapsed_ms"] = round((time.time() - started) * 1000, 2)
    with open(os.path.join(trace, "hooks.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


if __name__ == "__main__":
    with contextlib.suppress(Exception):  # a recorder failure must never touch the session
        main()
    sys.exit(0)
