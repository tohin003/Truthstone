"""The harness's logging hook, installed identically in both arms. Stdlib only.

Codex runs it for every hook event with the payload on stdin. It appends one line per
event to ``$HOOK_TRACE_DIR/hooks.jsonl`` and, on ``Stop``, copies the working tree to
``$HOOK_TRACE_DIR/stop-<n>/`` so the grader can later ask whether the hidden tests passed
at the very moment a completion gate held the turn (a *false block* if they did).

It never writes to stdout and always exits 0: anything else could change what Codex does,
and exit code 2 would be read as "block".
"""

import contextlib
import json
import os
import shutil
import sys
import time

TRACE_ENV = "HOOK_TRACE_DIR"
SKIP = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
MAX_SNAPSHOT_FILES = 5000


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
    }
    os.makedirs(trace, exist_ok=True)
    if event == "Stop" and payload.get("cwd"):
        existing = [d for d in os.listdir(trace) if d.startswith("stop-")]
        dest = os.path.join(trace, f"stop-{len(existing) + 1}")
        _snapshot(payload["cwd"], dest)
        record["snapshot"] = os.path.basename(dest)
    record["elapsed_ms"] = round((time.time() - started) * 1000, 2)
    with open(os.path.join(trace, "hooks.jsonl"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


if __name__ == "__main__":
    with contextlib.suppress(Exception):  # a recorder failure must never touch the session
        main()
    sys.exit(0)
