"""Every product-specific name the benchmark depends on, in one place.

The product is Truthstone (previously named AgentGuard). Nothing else in
`truthstone.bench.codex` may spell its name, its environment variables, its plugin ids or
the text its reasons carry: they all come from here, derived from `truthstone.names` (the
product's own record of its names) and `core.config`.
"""

from __future__ import annotations

import re

from truthstone import names as _names
from truthstone.core import config as _core_config

# The name. The display form is what the product's own messages say.
PRODUCT = _names.SLUG
PRODUCT_DISPLAY = _names.DISPLAY

# Environment variables the product reads. Imported, never re-spelled.
ENV_HOME = _core_config.ENV_HOME  # per-arm state directory
ENV_OBSERVE = _core_config.ENV_OBSERVE  # not used by the harness: see guards.py

# The product's on-disk layout inside its home.
CONFIG_FILENAME = "config.toml"
# The database inside an arm's home, spelled as core.config.database_path() spells it. Never
# call database_path() here: in the harness process (no product home set) it resolves the
# user's own home, and after the rename it falls back to the former name's database.
DB_FILENAME = f"{PRODUCT}.db"

# The Codex plugin, as the plugin builder lays it out in the repository.
PLUGIN_NAME = PRODUCT
MARKETPLACE_RELATIVE = ".agents/plugins/marketplace.json"
PLUGIN_RELATIVE = f"plugins/{PRODUCT}"
PLUGIN_MANIFEST_RELATIVE = ".codex-plugin/plugin.json"

# How the product's words can be recognised when they reach the model. Used only to
# reconcile model-visible interventions against the product's own decision log, never to
# score an outcome.
MODEL_VISIBLE_MARKER = re.compile(re.escape(PRODUCT_DISPLAY), re.IGNORECASE)

# The harness's own environment variable for its logging hook (not the product's). Bland
# on purpose: the agent can read its environment, and this must not announce a benchmark.
ENV_RECORD_DIR = "HOOK_TRACE_DIR"

# Environment the Codex plugin's launcher reads (plugins/<name>/hooks/<name>-hook.sh).
ENV_CODEX_HOOK = f"{_names.UPPER}_CODEX_HOOK"
ENV_NO_BOOTSTRAP = f"{_names.UPPER}_NO_BOOTSTRAP"
HOOK_RUNTIME_SCRIPT = f"{PRODUCT}-codex-hook"
CODEX_LAUNCHER = f"{PRODUCT}-hook.sh"  # inside the plugin's hooks/ directory
CLI_SCRIPT = PRODUCT
MARKETPLACE_NAME = PRODUCT
PLUGIN_ID = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"

# The Claude Code plugin (loaded per session with --plugin-dir) and what its hook.sh reads:
# the runtime to install (a local path means an editable install of the build under test)
# and the uv to install it with.
CLAUDE_PLUGIN_RELATIVE = f"plugins/{PRODUCT}-claude"
ENV_RUNTIME_SPEC = f"{_names.UPPER}_RUNTIME_SPEC"
ENV_UV = f"{_names.UPPER}_UV"
