"""Paired live benchmark of AgentGuard's Codex plugin: guarded versus observe-only.

The existing Claude harness (`agentguard.bench.runner`) is untouched by this package.

Modules
-------
naming        every product-specific name, in one place (the product will be renamed)
suite         task loading, materialisation, content snapshots
claims        the structured FINAL-line claim oracle
grader        hidden tests and declared rules; the single definition of false completion
scripted      scripted solutions and the grader validation that gates every run
transcript    reading `codex exec --json` streams and session rollouts
appserver     a minimal client for `codex app-server` (hooks, trust, usage windows)
homes         isolated CODEX_HOME, AGENTGUARD_HOME and login-shell homes
guards        the guard under test, behind a small install/attest/collect interface
agents        the Codex agent driver and the scripted agent used for dry runs
limits        ChatGPT plan usage windows, the budget rule and usage-limit detection
plan          pre-registered run plans and the interleaved cell order
orchestrator  the checkpointed cell loop
stats         exact McNemar, Clopper-Pearson, cluster bootstrap, Holm
report        analysis and the markdown report

Run with ``python -m agentguard.bench.codex --help``.
"""
