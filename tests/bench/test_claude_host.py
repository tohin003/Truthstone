"""The Claude Code host: stream parsing, account windows and rules, and the cell loop.

No model and no Claude Code: streams are synthetic, accounts are simulated.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
from pathlib import Path

import pytest

from truthstone.bench.codex import agents, claude, guards, orchestrator, report, suite, transcript
from truthstone.bench.codex.plan import Plan

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
TASKS = ["ledger-tax-rounding", "ledger-impossible-cap"]


def _write(path: Path, events: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return path


def _hook(event: str, stdout: str = "", exit_code: int = 0, stderr: str = "") -> dict:
    return {
        "type": "system",
        "subtype": "hook_response",
        "hook_event": event,
        "hook_name": event,
        "stdout": stdout,
        "output": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "outcome": "success",
    }


def _deny(decision: str, reason: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        }
    )


# -- the stream ------------------------------------------------------------------


def test_read_claude_stream_counts_requests_tools_tests_and_interventions(tmp_path):
    usage = {
        "input_tokens": 5,
        "cache_read_input_tokens": 1000,
        "cache_creation_input_tokens": 50,
        "output_tokens": 70,
    }
    events = [
        {
            "type": "system",
            "subtype": "init",
            "session_id": "s1",
            "model": "claude-opus-5-5",
            "permissionMode": "bypassPermissions",
            "claude_code_version": "2.1.318",
        },
        _hook("SessionStart"),
        # one request split over two assistant events (same message id): counted once
        {
            "type": "assistant",
            "message": {"id": "m1", "usage": usage, "content": [{"type": "text", "text": "hi"}]},
        },
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "usage": usage,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "python -m pytest -q"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True}]},
        },
        {
            "type": "assistant",
            "message": {
                "id": "m2",
                "usage": usage,
                "content": [
                    {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "/r/src/a.py"}}
                ],
            },
        },
        _hook("PreToolUse", _deny("deny", "Truthstone: no")),
        _hook("PreToolUse", _deny("ask", "Truthstone: confirm first")),  # headless ask = refusal
        _hook("PreToolUse", "", exit_code=2, stderr="Truthstone: exit-2 block"),
        _hook("PostToolUse", json.dumps({"decision": "block", "reason": "Truthstone: that broke a test"})),
        _hook("Stop", json.dumps({"decision": "block", "reason": "Truthstone: run the tests"})),
        _hook(
            "UserPromptSubmit",
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": "plan first",
                    }
                }
            ),
        ),
        _hook("Stop", json.dumps({"systemMessage": "developer-only note"})),  # never model-visible
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "rateLimitType": "five_hour",
                "overageStatus": "rejected",
                "isUsingOverage": False,
                "unifiedWindows": {
                    "five_hour": {"utilization": 0.42, "resetsAt": 1793743200, "status": "allowed"},
                    "seven_day": {"utilization": 0.2, "resetsAt": 1793876400, "status": "allowed"},
                },
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 1234,
            "result": "Done.\nFINAL: done",
        },
    ]
    t = transcript.read_claude_stream(_write(tmp_path / "s.jsonl", events))
    assert (t.model, t.cli_version, t.approval_policy) == ("claude-opus-5-5", "2.1.318", "bypassPermissions")
    assert t.model_requests == 2
    assert t.usage == {
        "input_tokens": 2110,  # all input: 10 uncached + 2000 cache reads + 100 writes
        "cached_input_tokens": 2000,
        "cache_write_input_tokens": 100,
        "output_tokens": 140,
    }
    assert [c.exit_code for c in t.commands] == [1]
    assert t.test_runs and t.test_runs[0].scope == "full"
    assert t.file_changes == [(2, "/r/src/a.py", "edit")]
    assert len(t.visible_denials) == 3
    assert t.post_tool_feedback == ["Truthstone: that broke a test"]
    assert t.stop_continuations == ["Truthstone: run the tests"]
    assert t.guard_context_messages == 1
    assert t.rate_limits_last["primary"]["used_percent"] == 42.0
    assert t.rate_limits_last["using_overage"] is False
    assert t.turns_completed == 1 and t.final_message.endswith("FINAL: done") and t.duration_ms == 1234
    assert not t.usage_limit_hit
    assert t.hook_events_reported["PreToolUse"] == 3


def test_a_rejected_rate_limit_or_limit_text_is_a_usage_limit(tmp_path):
    rejected = [
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "unifiedWindows": {"five_hour": {"utilization": 1.0, "resetsAt": 1, "status": "rejected"}},
            },
        }
    ]
    assert transcript.read_claude_stream(_write(tmp_path / "a.jsonl", rejected)).usage_limit_hit
    text = [
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "result": "You've hit your limit · resets 4pm (Asia/Calcutta)",
        }
    ]
    t = transcript.read_claude_stream(_write(tmp_path / "b.jsonl", text))
    assert t.usage_limit_hit and t.turns_completed == 0


# -- usage windows ---------------------------------------------------------------

USAGE = """Current session: 42% used · resets Nov 4 at 3:49pm (Asia/Calcutta)
Current week (all models): 35% used · resets Nov 5 at 4:29pm (Asia/Calcutta)
"""


def test_parse_usage_and_reset_times():
    now = dt.datetime(2026, 11, 4, 11, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))).timestamp()
    reading = claude.parse_usage(USAGE, now=now)
    assert reading["session"]["used_percent"] == 42.0 and reading["week"]["used_percent"] == 35.0
    expected = dt.datetime(2026, 11, 4, 15, 49, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    assert reading["session"]["resets_at"] == expected.timestamp()
    assert claude.parse_usage("no windows here") is None
    assert claude.parse_reset("Jan 2 at 9am (UTC)", now=now) > now  # rolls into next year


def _reading(session: float, week: float, resets_in: float = 3600.0, now: float = 1_000_000.0) -> dict:
    return {
        "session": {"used_percent": session, "resets_at": now + resets_in},
        "week": {"used_percent": week, "resets_at": now + 86400},
    }


def test_the_98_percent_rule_and_the_personal_reserve():
    policy = claude.AccountPolicy()
    now = 1_000_000.0
    # work at 98% may not start a cell; personal is under its 70% reserve: personal it is.
    choice = claude.choose_account(
        {"work": _reading(98.0, 10), "personal": _reading(50, 10)}, policy, now=now
    )
    assert choice.account == "personal"
    # personal at 70% is reserved even though 70 < 98.
    choice = claude.choose_account(
        {"work": _reading(97.9, 10), "personal": _reading(70, 10)}, policy, now=now
    )
    assert choice.account == "work"
    # personal's weekly window at 85% takes it out for the rest of the study.
    choice = claude.choose_account({"personal": _reading(5, 85)}, policy, now=now)
    assert choice.account is None and choice.wait_s == 0
    # both blocked by their 5-hour windows: wait for the earliest reset (plus slack).
    choice = claude.choose_account(
        {"work": _reading(99, 10, resets_in=900), "personal": _reading(75, 10, resets_in=3000)},
        policy,
        now=now,
    )
    assert choice.account is None and choice.wait_s == 900 + policy.reset_slack_s
    # more headroom wins when both are eligible
    choice = claude.choose_account({"work": _reading(40, 35), "personal": _reading(18, 37)}, policy, now=now)
    assert choice.account == "work"  # min(98-40, 95-35)=58 > min(70-18, 85-37)=48


def test_a_pair_is_admitted_only_if_its_second_cell_may_start():
    policy = claude.AccountPolicy(per_cell_session=2.0)
    ok, _ = claude.cell_allowed("work", _reading(95.5, 10), policy, cells=1)
    assert ok
    ok, why = claude.cell_allowed("work", _reading(96.5, 10), policy, cells=2)
    assert not ok and "98" in why
    ok, _ = claude.cell_allowed("work", {**_reading(10, 10), "rejected": True}, policy)
    assert not ok


# -- the cell loop ---------------------------------------------------------------


def _claude_plan(**kw) -> Plan:
    tasks = suite.load_suite(only=TASKS)
    base = dict(
        name="c",
        stage="dry-run",
        seed=3,
        tasks=TASKS,
        phrasings=["canonical"],
        replicates=[1, 2],
        model="scripted",
        effort="medium",
        suite_digest=suite.suite_digest(tasks),
        host="claude",
        accounts=["work", "personal"],
        budget=dataclasses.asdict(claude.AccountPolicy(per_cell_session=1.0, per_cell_week=0.1)),
    )
    base.update(kw)
    return Plan(**base)


def _claude_runner(tmp_path: Path, fake: claude.FakeAccounts, plan: Plan | None = None, interrupt=None):
    plan = plan or _claude_plan()
    agent = agents.ScriptedAgent(
        agents.dry_run_policy(seed=1, base_fc=1.0, catch=1.0),
        PYTHON,
        model="scripted",
        effort="medium",
        host="claude",
        accounts=fake,
        interrupt=interrupt,
    )
    runner = orchestrator.Runner(
        plan,
        {t.id: t for t in suite.load_suite(only=plan.tasks)},
        guards.FakeGuard(),
        agent,
        tmp_path / "run",
        tmp_path / "work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
    )
    runner.account_reader = fake.read
    runner.account_policy = plan.account_policy()
    runner.sleep = fake.sleep
    return runner


def _cells(run_dir: Path) -> list[dict]:
    return [r for r in orchestrator.load_records(run_dir / "cells.jsonl") if r.get("kind") == "cell"]


def test_claude_cells_record_their_account_and_pairs_never_straddle_accounts(tmp_path):
    fake = claude.FakeAccounts(
        {"work": (95.0, 10.0), "personal": (20.0, 10.0)}, per_cell=1.0, per_cell_week=0.1
    )
    runner = _claude_runner(tmp_path, fake)
    assert runner.run()["pairs_run"] == 4
    cells = _cells(tmp_path / "run")
    assert all(c["status"] == "valid" for c in cells) and all(c["account"] for c in cells)
    by_pair: dict[str, set] = {}
    for c in cells:
        by_pair.setdefault(c["pair_id"], set()).add(c["account"])
    assert all(len(v) == 1 for v in by_pair.values())
    assert {c["effort"] for c in cells} == {"medium"}
    assert {tuple(c["permission_modes"]) for c in cells} == {("bypassPermissions",)}
    # personal (headroom 50) beats work (headroom 3) until it nears its reserve
    assert cells[0]["account"] == "personal"
    usage_log = (tmp_path / "run" / "usage.jsonl").read_text().splitlines()
    assert usage_log, "the runner reads /usage before the study"
    analysis = report.analyze(tmp_path / "run")
    assert analysis["data_quality"]["cells_by_account"] == {"personal": 8}
    assert report.render_markdown(analysis).startswith("# Claude Code benchmark")


def test_a_429_mid_cell_voids_the_pair_and_it_reruns_without_spending_an_attempt(tmp_path):
    fake = claude.FakeAccounts({"work": (10.0, 10.0), "personal": (10.0, 10.0)})
    plan = _claude_plan()
    first = plan.schedule()[0][0].id
    runner = _claude_runner(tmp_path, fake, plan, interrupt={first})
    assert runner.run()["pairs_run"] == 4
    cells = _cells(tmp_path / "run")
    voids = [c for c in cells if c["status"] != "valid"]
    assert [c["void_reason"] for c in voids] == ["usage_limit"]
    assert voids[0]["pair_id"] == first
    states = orchestrator.pair_states(orchestrator.load_records(tmp_path / "run" / "cells.jsonl"), 3)
    assert states[first].complete and states[first].attempts == 0


def test_no_cell_starts_at_98_percent_the_runner_waits_for_the_reset(tmp_path):
    # work only, starting at 96.5% with 1.0 per cell: the second pair must wait for a reset.
    fake = claude.FakeAccounts({"work": (96.5, 10.0)}, per_cell=1.0, per_cell_week=0.1)
    plan = _claude_plan(
        accounts=["work"], budget=dataclasses.asdict(claude.AccountPolicy(per_cell_session=1.0))
    )
    runner = _claude_runner(tmp_path, fake, plan)
    assert runner.run()["pairs_run"] == 4
    assert fake.waited_s > 0 and fake.resets >= 1
    for c in _cells(tmp_path / "run"):
        before = c.get("limits_before")  # None for fake runs; the stream reading is the check
        assert before is None
    # every cell's own stream reading shows the window it ran in stayed under the cap
    starts = [c["limits_after"]["primary"]["used_percent"] - 1.0 for c in _cells(tmp_path / "run")]
    assert max(starts) < 98.0


def test_a_cell_that_crosses_the_cap_defers_the_pairs_second_cell(tmp_path):
    # per_cell_session unknown (0): admission adds no margin, so the second cell is deferred.
    fake = claude.FakeAccounts({"work": (97.5, 10.0)}, per_cell=1.0, per_cell_week=0.1)
    plan = _claude_plan(
        accounts=["work"],
        replicates=[1],
        budget=dataclasses.asdict(claude.AccountPolicy(per_cell_session=0.0)),
    )
    runner = _claude_runner(tmp_path, fake, plan)
    runner.run()
    cells = _cells(tmp_path / "run")
    deferred = [c for c in cells if c.get("problems") and "not started" in c["problems"][0]]
    assert deferred and deferred[0]["void_reason"] == "usage_limit"
    assert all(c["status"] == "valid" for c in cells if c not in deferred)


def test_paid_overage_halts(tmp_path):
    class OverageAgent(agents.ScriptedAgent):
        def _claude_stream(self, cell_dir, *a, **kw):
            path = super()._claude_stream(cell_dir, *a, **kw)
            lines = []
            for line in path.read_text().splitlines():
                event = json.loads(line)
                if event.get("type") == "rate_limit_event":
                    event["rate_limit_info"]["isUsingOverage"] = True
                lines.append(json.dumps(event))
            path.write_text("\n".join(lines) + "\n")
            return path

    fake = claude.FakeAccounts({"work": (10.0, 10.0)})
    plan = _claude_plan(accounts=["work"])
    runner = _claude_runner(tmp_path, fake, plan)
    runner.agent = OverageAgent(
        agents.dry_run_policy(seed=1), PYTHON, model="scripted", host="claude", accounts=fake
    )
    with pytest.raises(orchestrator.Halt, match="overage"):
        runner.run()


def test_an_observe_arm_that_injects_context_halts(tmp_path):
    class ChattyAgent(agents.ScriptedAgent):
        def _claude_stream(self, cell_dir, message, continued, observe_only, *a, **kw):
            path = super()._claude_stream(cell_dir, message, continued, observe_only, *a, **kw)
            if observe_only:
                extra = _hook("UserPromptSubmit", "plain stdout becomes context on this event")
                path.write_text(path.read_text() + json.dumps(extra) + "\n")
            return path

    fake = claude.FakeAccounts({"work": (10.0, 10.0)})
    plan = _claude_plan(accounts=["work"])
    runner = _claude_runner(tmp_path, fake, plan)
    runner.agent = ChattyAgent(
        agents.dry_run_policy(seed=1), PYTHON, model="scripted", host="claude", accounts=fake
    )
    with pytest.raises(orchestrator.Halt, match="leaked"):
        runner.run()


def test_a_claude_plan_names_accounts_and_keeps_codex_digests_stable():
    with pytest.raises(ValueError, match="accounts"):
        _claude_plan(accounts=[])
    # The Codex smoke plan registered before the product rename still loads, and its
    # recorded digest is reproduced under the former name's spelling of the build-ref field.
    smoke = Plan.load(suite.BENCH_ROOT / "plans" / "codex-smoke.json")
    assert smoke.host == "codex" and smoke.digest(spelling=1).startswith("008142a8")
    assert smoke.registered_digests()[1] == smoke.digest(spelling=1)
    tampered = json.loads((suite.BENCH_ROOT / "plans" / "codex-smoke.json").read_text())
    tampered["plan"]["seed"] += 1
    with pytest.raises(ValueError, match="digest"):
        path = suite.BENCH_ROOT / "plans" / "tampered.json"
        try:
            path.write_text(json.dumps(tampered))
            Plan.load(path)
        finally:
            path.unlink(missing_ok=True)
    with pytest.raises(ValueError):
        _claude_plan().budget_policy()
    assert _claude_plan().account_policy().start_max_session == 98.0


def test_claude_cells_get_claude_md_with_the_shared_protocol(tmp_path):
    task = suite.load_suite(only=["ledger-tax-rounding"])[0]
    made = suite.materialize(task, tmp_path / "w", tmp_path / "p", python=PYTHON, instructions="CLAUDE.md")
    assert (made.repo / "CLAUDE.md").read_text() == (suite.protocol_root() / "AGENTS.md").read_text()
    assert not (made.repo / "AGENTS.md").exists()


def test_the_arm_database_name_is_the_one_the_product_uses_inside_an_explicit_home(tmp_path, monkeypatch):
    # Regression: computed from database_path() in the harness process, the name followed
    # the user's own (former-name) home and every arm's evidence came back empty.
    from truthstone import names
    from truthstone.bench.codex import naming
    from truthstone.core import config

    monkeypatch.setenv(naming.ENV_HOME, str(tmp_path))
    for former in names.FORMER:
        monkeypatch.delenv(f"{former[2]}_HOME", raising=False)
    assert config.database_path() == tmp_path / naming.DB_FILENAME
