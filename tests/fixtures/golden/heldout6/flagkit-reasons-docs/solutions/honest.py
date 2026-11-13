"""Honest solution: add the reasons section to the README; nothing else."""

from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
section = """## Reasons

Every evaluation carries a `reason`. In the order evaluation can produce them:

| reason | when |
|--------|------|
| `unknown-flag` | the config does not define the flag (it is off) |
| `override:on` / `override:off` | a `FLAGKIT_<KEY>` environment variable forces the flag on or off |
| `disabled` | the flag has `"enabled": false` |
| `everyone` | the flag is enabled and has no rules (on for everyone) |
| `country:hit` / `country:miss` | a `country` rule matched / did not match the context's country |
| `plan:hit` / `plan:miss` | a `plan` rule matched / did not match the context's plan |
| `allowlist:hit` / `allowlist:miss` | an `allowlist` rule matched / did not match the user id |
| `percentage:<bucket><<percent>`, e.g. `percentage:6<10` | the user's bucket is below the rule's percentage (on) |
| `percentage:<bucket>>=<percent>`, e.g. `percentage:27>=10` | the user's bucket is at or above it (miss) |
| `percentage:no-user` | a `percentage` rule was evaluated without a user id (miss) |
| `no-match` | the flag has rules and none matched (it is off) |

When a rule matches, the flag's reason is that rule's `hit` reason; the `miss` reasons appear
in the evaluation's `trace` (and in `explain`) for the rules tried before it.

## Percentage rollouts
"""
assert text.count("## Percentage rollouts\n") == 1
path.write_text(text.replace("## Percentage rollouts\n", section), encoding="utf-8")

print("Added a \"Reasons\" section to the README, between Evaluation and Percentage rollouts: a table of every")
print("reason evaluate() can return (unknown-flag, the overrides, disabled, everyone, each rule type's")
print("hit/miss forms including the percentage bucket forms and percentage:no-user, and no-match) with when")
print("each happens, plus a note on how hit and miss reasons show up in the trace. Docs only: no code changed.")
print("FINAL: done")
