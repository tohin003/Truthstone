"""Amendment G5: two Codex accounts, the dedicated one preferred, reserves on the user's own.

No model and no real login is touched: readings are synthetic, and the only auth file is a
dummy written here (the harness only ever symlinks such a file, never reads it)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from truthstone.bench.codex import accounts, agents, cli, guards, homes, orchestrator, report, suite
from truthstone.bench.codex.plan import Plan

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
POLICY = accounts.CodexAccountPolicy()


def reading(primary: float, week: float, **extra) -> dict:
    now = time.time()
    return {
        "plan_type": "plus",
        "primary": {"used_percent": primary, "resets_at": now + 600},
        "secondary": {"used_percent": week, "resets_at": now + 86400},
        **extra,
    }


@pytest.mark.parametrize(
    "readings, chosen",
    [
        ({"p": reading(0, 0), "main": reading(0, 0)}, "p"),  # the dedicated account first
        ({"p": reading(10, 79.95), "main": reading(10, 10)}, "main"),  # p's pair would cross 80%
        ({"p": reading(97.6, 10), "main": reading(10, 10)}, "main"),  # p's pair would cross 98%
        ({"p": reading(10, 80), "main": reading(10, 50)}, None),  # main's weekly reserve
        ({"p": reading(10, 80), "main": reading(80, 10)}, None),  # main's 5-hour reserve
        ({"p": reading(10, 10, limit_reached=True), "main": reading(10, 10)}, "main"),
        ({"p": None, "main": reading(10, 10)}, "main"),  # an unreadable account is skipped
    ],
)
def test_selection_prefers_p_and_keeps_mains_reserves(readings, chosen):
    assert accounts.choose(readings, POLICY).account == chosen


def test_main_is_never_scheduled_at_its_reserves_and_p_never_at_98():
    assert not accounts.cell_allowed("main", reading(10, 50), POLICY)[0]
    assert not accounts.cell_allowed("main", reading(80, 10), POLICY)[0]
    assert accounts.cell_allowed("main", reading(79.9, 49.9), POLICY)[0]
    assert not accounts.cell_allowed("p", reading(98, 10), POLICY)[0]
    assert not accounts.cell_allowed("p", reading(10, 80), POLICY)[0]
    assert accounts.cell_allowed("p", reading(97.9, 79.9), POLICY)[0]


def test_a_5_hour_wait_but_never_a_weekly_one():
    waiting = accounts.choose({"p": reading(97.9, 10), "main": reading(10, 60)}, POLICY)
    assert waiting.account is None and 0 < waiting.wait_s <= 600 + POLICY.reset_slack_s
    done = accounts.choose({"p": reading(10, 80), "main": reading(10, 60)}, POLICY)
    assert done.account is None and done.wait_s == 0


def test_capacity_counts_cells_before_each_weekly_stop():
    assert accounts.capacity("p", reading(0, 0), POLICY) == 800
    assert accounts.capacity("main", reading(0, 40), POLICY) == 100
    assert accounts.capacity("main", reading(0, 55), POLICY) == 0


def test_each_account_links_its_own_login_and_never_reads_it(tmp_path, monkeypatch):
    login = tmp_path / "codex-p" / "auth.json"
    login.parent.mkdir()
    login.write_text("dummy, never read\n")
    login.chmod(0o000)  # unreadable: linking must not need to read it
    monkeypatch.setitem(accounts.ACCOUNTS, "p", login.parent)
    assert accounts.auth_source("p") == login
    assert accounts.auth_source("main") == Path.home() / ".codex" / "auth.json"
    assert accounts.auth_source(None) == homes.DEFAULT_AUTH_SOURCE
    with pytest.raises(ValueError):
        accounts.auth_source("work")
    template = homes.private_dir(tmp_path / "template")
    cell = homes.clone_codex_home(template, tmp_path / "cell", source=accounts.auth_source("p"))
    assert os.readlink(cell / "auth.json") == str(login)
    home = accounts.account_home(tmp_path / "state", "p")
    assert homes.auth_link_intact(home, login)
    login.chmod(0o600)


def test_plans_name_codex_accounts_and_old_plans_keep_their_digest():
    base = dict(
        name="x",
        stage="dry-run",
        seed=1,
        tasks=["ledger-tax-rounding"],
        phrasings=["canonical"],
        replicates=[0],
    )
    legacy = Plan(**base)
    assert not legacy.uses_accounts and legacy.budget_policy()
    multi = Plan(**base, accounts=["p", "main"], budget={"per_cell_week": 0.1})
    assert multi.uses_accounts and isinstance(multi.account_policy(), accounts.CodexAccountPolicy)
    assert multi.digest() != legacy.digest()
    with pytest.raises(ValueError):
        multi.budget_policy()
    with pytest.raises(ValueError, match="unknown Codex account"):
        Plan(**base, accounts=["work"])


class _Usage:
    """Each read of an account moves its weekly window, as cells spend it."""

    def __init__(self, start: dict[str, tuple[float, float]], step: dict[str, float]):
        self.state = dict(start)
        self.step = step

    def __call__(self, account: str) -> dict:
        primary, week = self.state[account]
        self.state[account] = (primary, week + self.step[account])
        return reading(primary, week)


def _runner(tmp_path: Path, usage: _Usage) -> orchestrator.Runner:
    tasks = suite.load_suite(only=["ledger-tax-rounding", "ledger-known-failure"])
    plan = Plan(
        name="acct",
        stage="dry-run",
        seed=3,
        tasks=[t.id for t in tasks],
        phrasings=["canonical", "terse"],
        replicates=[0, 1],
        model="scripted",
        suite_digest=suite.suite_digest(tasks),
        accounts=["p", "main"],
        budget={"per_cell_week": 0.1, "usage_refresh_s": 0},
    )
    runner = orchestrator.Runner(
        plan,
        {t.id: t for t in tasks},
        guards.FakeGuard(),
        agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=0.5), PYTHON),
        tmp_path / "acct",
        tmp_path / "acct-work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
        account_reader=usage,
        account_policy=plan.account_policy(),
    )
    return runner


def test_pairs_run_on_one_account_p_first_then_main_and_analysis_strata(tmp_path):
    usage = _Usage({"p": (5.0, 79.0), "main": (5.0, 49.0)}, step={"p": 0.25, "main": 0.05})
    runner = _runner(tmp_path, usage)
    summary = runner.run()
    cells = [r for r in orchestrator.load_records(runner.cells_path) if r.get("kind") == "cell"]
    by_pair: dict[str, set] = {}
    for c in cells:
        by_pair.setdefault(c["pair_id"], set()).add(c["account"])
    assert all(len(found) == 1 for found in by_pair.values())  # a pair never spans accounts
    order = [c["account"] for c in cells]
    assert order[0] == "p" and "main" in order and order.index("main") > order.index("p")
    assert "p" not in order[order.index("main") :]  # p is never used again once past its stop
    assert summary["pairs_run"] == 8 and not summary["stopped"]
    # and once main's reserve is reached too, nothing more starts
    stop = accounts.choose({"p": reading(5, 80), "main": reading(5, 49.95)}, runner.plan.account_policy())
    assert stop.account is None
    analysis = report.analyze(runner.run_dir)
    assert set(analysis["accounts"]) <= {"p", "main"}


def test_allowance_reports_both_accounts_and_the_combined_capacity(tmp_path, monkeypatch, capsys):
    fake = {"p": reading(0, 10), "main": reading(0, 45)}
    monkeypatch.setattr(cli, "read_allowance", lambda codex_bin, account=None: fake.get(account))
    data = cli._codex_accounts_report("codex")
    assert data["accounts"]["p"]["cells_before_weekly_stop"] == 700
    assert data["accounts"]["main"]["cells_before_weekly_stop"] == 50
    assert data["combined_capacity"] == 750
    plan = Plan(
        name="acct-plan",
        stage="main",
        seed=1,
        tasks=["ledger-tax-rounding"],
        phrasings=["canonical"],
        replicates=[0],
        accounts=["p", "main"],
    )
    plan.save(tmp_path / "plan.json")
    status = cli.main(["allowance", "--plan", str(tmp_path / "plan.json"), "--run-dir", str(tmp_path / "r")])
    out = capsys.readouterr().out
    assert status == 0 and "account p:" in out and "account main:" in out and "combined capacity: 750" in out
