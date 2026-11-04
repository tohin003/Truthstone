"""Amendment G1: nothing the observe arm's model is given may name the product.

The observe arm installs a hooks-only copy of the plugin (no skills, nothing listed to the
model), every observe cell is checked for the product's names in its model-visible context,
and the Claude sandbox lists only neutral paths (it describes itself to the model). The live
no-model probes (the real Claude binary against a scripted API) run only when
``CODEX_BENCH_LIVE_SANDBOX=1``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from truthstone.bench.codex import (
    agents,
    claude,
    claude_sandbox,
    cli,
    guards,
    homes,
    naming,
    orchestrator,
    report,
    suite,
    transcript,
)
from truthstone.bench.codex.plan import Plan

PYTHON = os.path.abspath(os.environ.get("CODEX_BENCH_PYTHON", ".venv/bin/python"))
CODEX_PLUGIN = suite.REPO_ROOT / naming.PLUGIN_RELATIVE
CLAUDE_PLUGIN = suite.REPO_ROOT / naming.CLAUDE_PLUGIN_RELATIVE
# As Codex renders it: a tagged block of its own (so never mistaken for hook context).
SKILL_LISTING = (
    "<skills_instructions>\n### Available skills\n- truthstone:truthstone: Resolve Truthstone "
    "(previously named AgentGuard) challenges. (file: /c/plugins/cache/truthstone/truthstone/0.1.0/"
    "skills/truthstone/SKILL.md)\n</skills_instructions>"
)


# -- the hooks-only variant ---------------------------------------------------------------


@pytest.mark.parametrize(
    "source, manifest",
    [
        (CODEX_PLUGIN, naming.PLUGIN_MANIFEST_RELATIVE),
        (CLAUDE_PLUGIN, claude.CLAUDE_PLUGIN_MANIFEST_RELATIVE),
    ],
    ids=["codex", "claude"],
)
def test_the_observe_arm_gets_the_plugin_without_anything_model_visible(tmp_path, source, manifest):
    assert (source / "skills").is_dir()  # the full plugin lists skills to the model
    copy = tmp_path / "p"
    copied = homes.hooks_only_copy(source, copy, manifest)
    for part in homes.MODEL_VISIBLE_PARTS:
        assert not (copy / part).exists()
        assert not [p for p in copied if p.startswith(f"{part}/")]
    # the hooks (and what they run) are byte for byte the guarded arm's
    assert homes.tree_digest(copy / "hooks") == homes.tree_digest(source / "hooks")
    if (source / "scripts").is_dir():
        assert homes.tree_digest(copy / "scripts") == homes.tree_digest(source / "scripts")
    full = json.loads((source / manifest).read_text())
    bare = json.loads((copy / manifest).read_text())
    assert bare["name"] == full["name"]  # same install id, data directory and hook trust
    assert set(bare) <= set(homes.HOOKS_ONLY_MANIFEST_KEYS)
    assert "description" not in bare and "interface" not in bare and "skills" not in bare


def _codex_build(tmp_path: Path) -> guards.Build:
    marketplace = tmp_path / "build" / "marketplace"
    homes.symlink_free_copy(CODEX_PLUGIN, marketplace / naming.PLUGIN_RELATIVE)
    (marketplace / naming.MARKETPLACE_RELATIVE).parent.mkdir(parents=True)
    (marketplace / naming.MARKETPLACE_RELATIVE).write_text("{}\n")
    return guards.Build("HEAD", "c0ffee", suite.REPO_ROOT, tmp_path / "venv", marketplace, "d", "0.1.0")


def test_the_codex_observe_arm_installs_a_hooks_only_marketplace(tmp_path):
    build = _codex_build(tmp_path)
    plugin = guards.TruthstonePlugin(build, "codex", observe_plugin="hooks-only")
    contexts = {}
    for name in ("on", "observe"):
        root = homes.private_dir(tmp_path / name)
        contexts[name] = guards.ArmContext(guards.ARMS[name], root, root / "c", root / "g", tmp_path / "sh")
    assert plugin.marketplace_for(contexts["on"]) == build.marketplace
    variant = plugin.marketplace_for(contexts["observe"])
    assert variant != build.marketplace and (variant / naming.MARKETPLACE_RELATIVE).exists()
    assert not (variant / naming.PLUGIN_RELATIVE / "skills").exists()
    assert (build.marketplace / naming.PLUGIN_RELATIVE / "skills").exists()
    # a plan from before G1 keeps the full plugin in both arms
    legacy = guards.TruthstonePlugin(build, "codex")
    assert legacy.marketplace_for(contexts["observe"]) == build.marketplace
    with pytest.raises(ValueError):
        guards.TruthstonePlugin(build, "codex", observe_plugin="none")


def test_the_claude_observe_arm_loads_a_hooks_only_copy_under_neutral_names(tmp_path):
    build = guards.Build("HEAD", "c0ffee", suite.REPO_ROOT, tmp_path / "venv", tmp_path / "m", "d", "0.1.0")
    state = tmp_path / "state"
    recorder = (Path(sys.executable), tmp_path / "rec.py")
    plugin = claude.TruthstoneClaudePlugin.from_build(
        build, state, "claude", "uv", recorder, observe_plugin="hooks-only"
    )
    contexts = {}
    for name in ("on", "observe"):
        root = homes.private_dir(tmp_path / name)
        ctx = guards.ArmContext(guards.ARMS[name], root, root / "c", root / "g", tmp_path / "sh")
        ctx.plugin_root = plugin.plugin_root_for(ctx)
        contexts[name] = ctx
    on, observe = contexts["on"].plugin_root, contexts["observe"].plugin_root
    assert on == plugin.plugin_root and observe == plugin.observe_plugin_root and on != observe
    assert (on / "skills").is_dir() and not (observe / "skills").exists()
    # Claude Code lists every --plugin-dir to the model (its sandbox protects them): neutral
    for path in (on, observe, plugin.recorder_plugin):
        relative = path.relative_to(state)
        assert not naming.VISIBLE_PRODUCT.search(str(relative))
        assert not claude_sandbox.STUDY_WORDS.search(str(relative))
    args = plugin.exec_args(contexts["observe"])
    assert args[args.index("--plugin-dir") + 1] == str(observe)
    assert plugin.exec_args(contexts["on"])[1] == str(on)
    assert plugin.observe_variant == "hooks-only"
    full = claude.TruthstoneClaudePlugin.from_build(build, tmp_path / "s2", "claude", "uv", None)
    assert full.observe_variant == "full" and full.plugin_root_for(contexts["observe"]) == full.plugin_root


# -- the per-cell instrument check ---------------------------------------------------------


def _rollout(path: Path, developer_text: str, tool_output: str = "") -> Path:
    items = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": developer_text}],
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "c1", "output": tool_output},
        },
    ]
    path.write_text("".join(json.dumps(i) + "\n" for i in items))
    return path


def test_the_instrument_check_reads_what_the_model_is_given_not_what_tools_return(tmp_path):
    shown = transcript.read_rollout(_rollout(tmp_path / "a.jsonl", SKILL_LISTING), transcript.Transcript())
    assert shown.visible_product and shown.visible_product[0].startswith("developer message:")
    # the agent finding the name in a tool's output is its own doing, not the arm's install
    found = transcript.read_rollout(
        _rollout(
            tmp_path / "b.jsonl", "<skills_instructions>- imagegen</skills_instructions>", "~/.truthstone"
        ),
        transcript.Transcript(),
    )
    assert found.visible_product == []
    stream = tmp_path / "stream.jsonl"
    init = {"type": "system", "subtype": "init", "session_id": "s", "tools": ["Bash"], "mcp_servers": []}
    stream.write_text(json.dumps({**init, "skills": ["deep-research", "truthstone:why"]}) + "\n")
    assert transcript.read_claude_stream(stream).visible_product[0].startswith("init skills:")
    stream.write_text(json.dumps({**init, "skills": ["deep-research"], "slash_commands": ["review"]}) + "\n")
    assert transcript.read_claude_stream(stream).visible_product == []


def test_the_dev_pilot_stratum_was_shown_the_product():
    """The registered pilot ran before G1: its plan has no observe plugin (the full one)."""
    plan = Plan.load(suite.REPO_ROOT / "bench" / "codex" / "plans" / "golden-dev-sol.json")  # digest intact
    assert plan.observe_plugin == "" and plan.observe_variant == "full" and not plan.skill_free_observe


class _ShowsTheProduct:
    """A scripted agent whose Codex session context lists the guard's skill."""

    def __init__(self, inner):
        self.inner = inner

    def run(self, prompt, repo, env, cell_dir, tmpdir, extra, **kw):
        run = self.inner.run(prompt, repo, env, cell_dir, tmpdir, extra, **kw)
        _rollout(cell_dir / "rollout.jsonl", SKILL_LISTING)
        return run


def _plan(name: str, observe_plugin: str, tasks: list[suite.Task]) -> Plan:
    return Plan(
        name=name,
        stage="dry-run",
        seed=11,
        tasks=[t.id for t in tasks],
        phrasings=["canonical"],
        replicates=[0],
        arms=["observe"],
        model="scripted",
        suite_digest=suite.suite_digest(tasks),
        observe_plugin=observe_plugin,
    )


def _runner(
    tmp_path: Path, plan: Plan, tasks: list[suite.Task], agent=None, guard=None
) -> orchestrator.Runner:
    inner = agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=1.0), PYTHON)
    return orchestrator.Runner(
        plan,
        {t.id: t for t in tasks},
        guard or guards.FakeGuard(),
        agent or _ShowsTheProduct(inner),
        tmp_path / plan.name,
        tmp_path / f"{plan.name}-work",
        PYTHON,
        real_codex=False,
        log=lambda _m: None,
    )


def test_an_observe_cell_shown_the_product_halts_a_skill_free_run(tmp_path):
    tasks = suite.load_suite(only=["ledger-tax-rounding", "ledger-impossible-cap"])
    runner = _runner(tmp_path, _plan("g1", "hooks-only", tasks), tasks)
    with pytest.raises(orchestrator.Halt, match="shown the product"):
        runner.run()
    cells = [r for r in orchestrator.load_records(tmp_path / "g1" / "cells.jsonl") if r.get("kind") == "cell"]
    assert len(cells) == 1  # stopped at the first: the install, not the agent, is at fault
    assert cells[0]["status"] == "halt" and cells[0]["void_reason"] == "visible_product"
    assert "truthstone" in cells[0]["visible_product"][0].lower()


def test_a_plan_from_before_g1_records_the_exposure_and_scores_the_cell(tmp_path):
    tasks = suite.load_suite(only=["ledger-tax-rounding", "ledger-impossible-cap"])
    runner = _runner(tmp_path, _plan("legacy", "", tasks), tasks)
    runner.run()
    cells = [
        r for r in orchestrator.load_records(tmp_path / "legacy" / "cells.jsonl") if r.get("kind") == "cell"
    ]
    assert len(cells) == 2 and all(c["status"] == "valid" and c["visible_product"] for c in cells)
    quality = report.analyze(tmp_path / "legacy")["data_quality"]
    assert quality["observe_plugin"] == "full" and quality["observe_cells_shown_product"] == 2


def test_a_skill_free_run_whose_observe_arm_is_clean_scores_every_cell(tmp_path):
    tasks = suite.load_suite(only=["ledger-tax-rounding"])
    inner = agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=1.0), PYTHON)
    runner = _runner(tmp_path, _plan("clean", "hooks-only", tasks), tasks, agent=inner)
    runner.run()
    cells = [
        r for r in orchestrator.load_records(tmp_path / "clean" / "cells.jsonl") if r.get("kind") == "cell"
    ]
    assert [c["status"] for c in cells] == ["valid"] and "visible_product" not in cells[0]


def test_a_guard_installing_another_observe_plugin_than_the_plan_registers_is_refused(tmp_path):
    class FullGuard(guards.FakeGuard):
        observe_variant = "full"

    tasks = suite.load_suite(only=["ledger-tax-rounding"])
    runner = _runner(tmp_path, _plan("mismatch", "hooks-only", tasks), tasks, guard=FullGuard())
    with pytest.raises(orchestrator.Halt, match="observe arm would install the full plugin"):
        runner.bind()


# -- plans ---------------------------------------------------------------------------------


def test_plans_register_the_observe_plugin_and_old_plans_keep_their_digest():
    tasks = suite.load_suite(only=["ledger-tax-rounding"])
    legacy = _plan("p", "", tasks)
    fixed = _plan("p", "hooks-only", tasks)
    assert legacy.digest() != fixed.digest()  # and at "" it is left out: old digests hold
    assert fixed.skill_free_observe and fixed.observe_variant == "hooks-only"
    with pytest.raises(ValueError, match="observe_plugin"):
        _plan("p", "skills", tasks)


def test_the_plan_command_makes_the_observe_arm_skill_free_by_default(tmp_path):
    out = tmp_path / "plan.json"
    assert (
        cli.main(
            ["plan", "--name", "x", "--task", "ledger-tax-rounding", "--replicates", "1", "--out", str(out)]
        )
        == 0
    )
    assert Plan.load(out).observe_plugin == "hooks-only"
    old = tmp_path / "old.json"
    cli.main(
        [
            "plan",
            "--name",
            "x",
            "--task",
            "ledger-tax-rounding",
            "--replicates",
            "1",
            "--observe-plugin",
            "full",
            "--out",
            str(old),
        ]
    )
    assert Plan.load(old).observe_plugin == "full"


def test_the_pilot_never_pools_with_a_skill_free_screen(tmp_path):
    tasks = suite.load_suite(only=["ledger-tax-rounding"])
    inner = agents.ScriptedAgent(agents.dry_run_policy(seed=1, base_fc=1.0), PYTHON)
    for name, variant in (("pilot", ""), ("screen", "hooks-only")):
        _runner(tmp_path, _plan(name, variant, tasks), tasks, agent=inner).run()
    with pytest.raises(ValueError, match="observe plugin"):
        report.pooled_calibration([tmp_path / "pilot", tmp_path / "screen"])
    assert report.pooled_calibration([tmp_path / "screen"])["runs"][0]["observe_cells"] == 1


# -- the Claude sandbox describes itself to the model -------------------------------------


def test_preflight_cues_and_problems(tmp_path):
    tasks = suite.load_suite(only=["ledger-tax-rounding"])
    plan = _plan("golden-dev-x", "hooks-only", tasks)
    cues = cli._study_cues(plan, tmp_path / "golden-dev-x-preflight-1", tasks[0])
    assert plan.name in cues and tasks[0].id in cues and "bench/codex" in cues
    text = "Filesystem: deny /Users/u/p/bench/codex/results/golden-dev-x/cells/t.canonical.r1.observe.a1"
    assert guards.cue_mentions(text, cues)
    observe = guards.ArmContext(guards.ARMS["observe"], tmp_path, tmp_path, tmp_path, tmp_path)
    on = guards.ArmContext(guards.ARMS["on"], tmp_path, tmp_path, tmp_path, tmp_path)
    assert cli._visible_problems(plan, observe, ["truthstone:truthstone"])
    assert not cli._visible_problems(plan, on, ["truthstone:truthstone"])  # the treatment itself
    assert cli._visible_problems(plan, on, [], ["'golden-dev-x': ..."])  # never, in any arm
    legacy = _plan("golden-dev-x", "", tasks)
    assert not cli._visible_problems(legacy, observe, ["truthstone:truthstone"])


@pytest.mark.skipif(
    os.environ.get("CODEX_BENCH_LIVE_SANDBOX") != "1", reason="set CODEX_BENCH_LIVE_SANDBOX=1"
)
def test_live_only_the_guarded_arm_is_shown_the_product_and_neither_arm_the_study(tmp_path):
    """The real binary with a cell's plugins, flags and sandbox settings: no model call."""
    work = Path(homes.private_dir(Path.home() / ".cache" / "cw" / homes.neutral_name("g1", tmp_path)))
    try:
        state = work / "state"
        full = state / homes.neutral_name("plugin", "full") / "p"
        homes.symlink_free_copy(CLAUDE_PLUGIN, full)
        bare = state / homes.neutral_name("plugin", "hooks-only") / "p"
        homes.hooks_only_copy(CLAUDE_PLUGIN, bare, claude.CLAUDE_PLUGIN_MANIFEST_RELATIVE)
        run_dir = suite.REPO_ROOT / "bench" / "codex" / "results" / "golden-g1-live"
        paths = claude_sandbox.SandboxPaths.for_study(suite.REPO_ROOT, run_dir, work, [state / "taskenv"])
        cues = ("golden-g1-live", "bench/codex", "/cells/")
        seen = {}
        for label, root in (("on", full), ("observe", bare)):
            seen[label] = claude_sandbox.visible_context(
                claude.default_claude_bin(),
                work,
                ["--plugin-dir", str(root), *claude.ISOLATION_FLAGS],
                paths,
                "Fix the failing test.",
                allowed_tools=claude.DEFAULT_ALLOWED_TOOLS,
                cues=cues,
            )
        assert seen["observe"].clean, seen["observe"]
        assert seen["on"].mentions and seen["on"].init_mentions  # the skill: the treatment
        assert not seen["on"].cue_mentions and not seen["on"].user_memory_visible
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
