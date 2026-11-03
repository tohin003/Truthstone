"""``python -m agentguard.bench.codex <command>``.

Commands that start a live model session require ``--confirm-live``; everything else
runs without any model call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentguard.bench.codex import scripted, suite


def _cmd_suite_list(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    for task in tasks:
        mech = ",".join(task.opportunity.mechanisms)
        print(f"{task.id:<34}{task.set:<11}{task.family:<24}{mech}")
    print(f"\n{len(tasks)} task(s); suite digest {suite.suite_digest(tasks)[:16]}")
    return 0


def _cmd_suite_validate(args: argparse.Namespace) -> int:
    tasks = suite.load_suite(only=args.task or None)
    # absolute, but not resolved: resolving a venv's python symlink would leave the venv
    python = os.path.abspath(args.python or scripted.default_python())
    failures = 0
    rows = []
    for task in tasks:
        result = scripted.validate_task(task, python)
        for v in result.variants:
            flag = "ok " if v.ok else "BAD"
            detail = (v.problem or ", ".join(v.reasons))[:90]
            print(f"{flag} {task.id:<34}{v.variant:<8}{v.outcome:<18}{detail}")
        failures += 0 if result.ok else 1
        rows.append({"task": task.id, "ok": result.ok,
                     "variants": [{s: getattr(v, s) for s in v.__slots__} for v in result.variants]})
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n{len(tasks) - failures}/{len(tasks)} task(s) validated")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agentguard.bench.codex")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List the task suite.")
    p_list.add_argument("--task", action="append")
    p_list.set_defaults(func=_cmd_suite_list)

    p_val = sub.add_parser("validate", help="Prove every grader on noop/honest/planted solutions.")
    p_val.add_argument("--task", action="append")
    p_val.add_argument("--python", help="Interpreter with pytest for the task code.")
    p_val.add_argument("--json", help="Write the validation table here.")
    p_val.set_defaults(func=_cmd_suite_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
