"""Every product-specific name the Codex benchmark depends on, in one place.

The product is due to be renamed. Nothing else in `agentguard.bench.codex` may spell the
working name, its environment variables, its plugin id or the text its reasons carry:
they all come from here, and the core ones are imported from `core.config`, so a rename
is one edit in each of two files rather than a search through the harness.
"""

from __future__ import annotations

import re

from agentguard.core import config as _core_config

# Working name. The display form is what the product's own messages say.
PRODUCT = "agentguard"
PRODUCT_DISPLAY = "AgentGuard"

# Environment variables the product reads. Imported, never re-spelled.
ENV_HOME = _core_config.ENV_HOME  # per-arm state directory
ENV_OBSERVE = _core_config.ENV_OBSERVE  # not used by the harness: see guards.py

# The product's on-disk layout inside its home.
CONFIG_FILENAME = "config.toml"
DB_FILENAME = _core_config.database_path().name  # "agentguard.db"

# The Codex plugin, as the plugin builder lays it out in the repository.
PLUGIN_NAME = PRODUCT
MARKETPLACE_RELATIVE = ".agents/plugins/marketplace.json"
PLUGIN_RELATIVE = f"plugins/{PRODUCT}"
PLUGIN_MANIFEST_RELATIVE = ".codex-plugin/plugin.json"

# How the product's words can be recognised when they reach the model. Used only to
# reconcile model-visible interventions against the product's own decision log, never to
# score an outcome.
MODEL_VISIBLE_MARKER = re.compile(re.escape(PRODUCT_DISPLAY), re.IGNORECASE)

# The harness's own environment variable for its logging hook (not the product's).
ENV_RECORD_DIR = "CODEX_BENCH_RECORD_DIR"
