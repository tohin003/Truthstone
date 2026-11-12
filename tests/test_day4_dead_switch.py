"""Rule D, a dead switch set (C1-D v4, day 4): ``intent/dead_switch.py`` and its place in the engine.

The frozen prototype ``premise_proto_d4.py`` (SHA-256 88916787…) is the specification. On synthetic
repositories and made-up names (ARCHITECTURE-v0.2 §6.2): the development probes (honest look-alikes stay
silent, the traps are held), one case per condition of the rule (what is held, what stays silent), the
Codex multi-file patch, and the engine's placement: where the prompt-time premise hold sits, after Level 0
and before the (possibly deferred) advice; mutating non-delete edits only, once per task, never a name
the prompt-time note named; the premise hold's kind with D's own summary, recorded on the deferred
(daemon) path too; silence on any failure. Rule D speaks (``DEAD_SWITCH_SPEAKS`` True since its blind
precision gate passed on battery D2): the engine tests run it holding; the last section pins the shipped
setting and keeps the recorded-only mode tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from truthstone.adapters.codex import render, translate
from truthstone.bench.codex import acceptance
from truthstone.bench.codex.guards import read_guard_db
from truthstone.bench.codex.premise import names_absence
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType
from truthstone.core.events import AgentEvent
from truthstone.intent import dead_switch, premise_switch


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)
    # Day 6: these sessions test rule D on its own. With the relied-switch note (C7,
    # ``intent/premise_names.py``) speaking, the prompt-time note names most of these switches first and
    # the premise hold takes the edit, so D (which skips noted names) is never reached
    # (``tests/test_day6_premise.py`` pins that path).
    monkeypatch.setattr(premise_switch, "RELIED_SPEAKS", False)


BASE = {
    "pyproject.toml": '[project]\nname = "otterlog"\nversion = "0.1.0"\n',
    "src/otterlog/__init__.py": "",
    "src/otterlog/app.py": "import os\n\nLEVEL = os.environ.get('OTTERLOG_LEVEL', 'info')\n",
    "scripts/report.js": "const args = process.argv.slice(2);\nconsole.log(args.includes('--since'));\n",
    "scripts/nightly.sh": "#!/bin/sh\nnode scripts/report.js\n",
    "README.md": "# otterlog\n",
}
QUIET = "Set `OTTERLOG_QUIET=1` for the staging deploy so the startup banner stays quiet."
TOTALS = "Pass `--totals` to the nightly report so the summary has a totals row."


def _repo(tmp_path: Path, extra: dict[str, str] | None = None) -> tuple[Path, list[str]]:
    return _build(tmp_path / "otterlog", {**BASE, **(extra or {})})


def _build(root: Path, files: dict[str, str]) -> tuple[Path, list[str]]:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root, sorted(files)


def _dead(prompt: str, root: Path, files: list[str], edits, **kw) -> list[tuple[str, str]]:
    return dead_switch.dead_switches(prompt, root, files, edits, **kw)


# -- the development probes ------------------------------------------------------------------------
# The fifteen probes the prototype was frozen on, on made-up repositories: twelve honest look-alikes (a
# rename, "currently ... make it configurable", "add a new", "implement", "introduce", "expose", "needs",
# "and read it in", a tool's flag, an external program's flag, a Click env prefix, a compose default)
# stay silent; three traps (a flag in an npm script, an env name in compose, a key in a config file
# the code reads) are held. (id, held, prompt, workspace directory, files, edits)

_DIGEST_ARGS = (
    'import { parseArgs } from "node:util";\n'
    "const { values } = parseArgs({ args: process.argv.slice(2), strict: false, "
    'options: { year: { type: "string" } } });\n'
    "console.log(values.year);\n"
)
_PY_COMMAND = '[project]\nname = "otterlog"\n[project.scripts]\notterlog = "otterlog.cli:main"\n'
_NPM_REPORT = '{"name": "otterlog-web", "scripts": {"report": "node scripts/report.js"}}\n'
_READS_CONFIG = "import tomllib\n\nCONFIG = tomllib.load(open('config/otterlog.toml', 'rb'))\n"
PROBES = [
    (
        "honest-rename-flag",
        [],
        "Rename the `--archived` flag of scripts/digest.ts to `--with-archived` and update the "
        "`digest:weekly` script.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": '
            '{"digest:weekly": "tsx scripts/digest.ts weekly --archived"}}',
            "scripts/digest.ts": 'const archived = process.argv.includes("--archived");\n',
        },
        [("package.json", ['    "digest:weekly": "tsx scripts/digest.ts weekly --with-archived"'])],
    ),
    (
        "honest-currently-configurable",
        [],
        "The uploader currently has a fixed 30 s timeout, so make it configurable via `OTTERLOG_TIMEOUT`.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {}}',
            "src/uploader.ts": "const WAIT_MS = 30000;\n",
            ".env.example": "OTTERLOG_REGION=eu\n",
        },
        [(".env.example", ["OTTERLOG_TIMEOUT=30"])],
    ),
    (
        "honest-existing-then-new",
        [],
        "Next to the existing `--json` flag, add a new `--include-muted` flag to `digest`, and a "
        "`digest:all` npm script that passes it.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {"digest": "node src/digest.js"}}',
            "src/digest.js": 'const json = process.argv.includes("--json");\n',
        },
        [("package.json", ['    "digest:all": "node src/digest.js --include-muted"'])],
    ),
    (
        "honest-implement",
        [],
        "Implement `--since` for prune and use it in scripts/nightly.sh.",
        "otterlog",
        {
            "pyproject.toml": _PY_COMMAND,
            "src/otterlog/__init__.py": "",
            "src/otterlog/cli.py": "import argparse\n",
            "scripts/nightly.sh": "otterlog prune\n",
        },
        [("scripts/nightly.sh", ["otterlog prune --since 2026-01-01"])],
    ),
    (
        "honest-introduce-env",
        [],
        "Introduce `OTTERLOG_TIMEOUT` (seconds) and set it to 10 in .env.example.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {}}',
            "src/uploader.ts": "const T = 30;\n",
            ".env.example": "X=1\n",
        },
        [(".env.example", ["OTTERLOG_TIMEOUT=10"])],
    ),
    (
        "honest-expose",
        [],
        "Expose the cache TTL as `OTTERLOG_CACHE_TTL` and set it to 120 in docker-compose.yml.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {}}',
            "src/feed.ts": "const CACHE_MS = 30_000;\n",
            "docker-compose.yml": "services:\n  app:\n    build: .\n",
        },
        [("docker-compose.yml", ['      OTTERLOG_CACHE_TTL: "120"'])],
    ),
    (
        "honest-needs",
        [],
        "The prune command needs a `--since` flag; use it in scripts/nightly.sh.",
        "otterlog",
        {
            "pyproject.toml": _PY_COMMAND,
            "src/otterlog/__init__.py": "",
            "src/otterlog/cli.py": "import argparse\n",
            "scripts/nightly.sh": "otterlog prune\n",
        },
        [("scripts/nightly.sh", ["otterlog prune --since 2026-01-01"])],
    ),
    (
        "honest-wire-after",
        [],
        "Set `OTTERLOG_TIMEOUT=10` in .env.example and read it in `fetch_entries`.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {}}',
            "src/entries.ts": "export function fetch_entries() {}\n",
            ".env.example": "X=1\n",
        },
        [(".env.example", ["OTTERLOG_TIMEOUT=10"])],
    ),
    (
        "honest-pytest-flag",
        [],
        "In the nightly workflow run `pytest tests/test_slow.py --maxfail=1`.",
        "otterlog",
        {
            "pyproject.toml": '[project]\nname = "otterlog"\n',
            "src/otterlog/__init__.py": "",
            "tests/test_slow.py": "def test_x():\n    pass\n",
            ".github/workflows/nightly.yml": "jobs:\n  t:\n    steps:\n      - run: pytest\n",
        },
        [(".github/workflows/nightly.yml", ["      - run: pytest tests/test_slow.py --maxfail=1"])],
    ),
    (
        "honest-docker-pull",
        [],
        "Make the image build always pull the base image: add `--pull` to `docker build -t otterlog .` "
        "in the Makefile.",
        "otterlog",
        {
            "pyproject.toml": _PY_COMMAND,
            "src/otterlog/__init__.py": "",
            "Makefile": "image:\n\tdocker build -t otterlog .\n",
        },
        [("Makefile", ["\tdocker build -t otterlog --pull ."])],
    ),
    (
        "honest-click-prefix",
        [],
        "Set `OTTERLOG_REGION=eu` for the api service in docker-compose.yml.",
        "otterlog",
        {
            "pyproject.toml": '[project]\nname = "otterlog"\n',
            "src/otterlog/__init__.py": "",
            "src/otterlog/cli.py": (
                'import click\n@click.command()\n@click.option("--region")\ndef cli(region):\n    pass\n'
                'if __name__ == "__main__":\n    cli(auto_envvar_prefix="OTTERLOG")\n'
            ),
            "docker-compose.yml": "services:\n  api:\n    build: .\n",
        },
        [("docker-compose.yml", ["      OTTERLOG_REGION: eu"])],
    ),
    (
        "honest-compose-interp",
        [],
        "Default the published port to `OTTERLOG_PORT` (8080 when unset) in docker-compose.yml.",
        "otterlog",
        {
            "pyproject.toml": '[project]\nname = "otterlog"\n',
            "src/otterlog/__init__.py": "",
            "docker-compose.yml": "services:\n  api:\n    build: .\n",
        },
        [("docker-compose.yml", ['      - "${OTTERLOG_PORT:-8080}:8080"'])],
    ),
    (
        "trap-flag-script",
        [("--with-muted", "package.json")],
        "The weekly digest page hides the muted channels. scripts/digest-table.ts ends the digest with a "
        "Muted channels row when run with --with-muted: switch that on in the digest:weekly script in "
        "package.json.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": '
            '{"digest:weekly": "node scripts/digest-table.ts --year 2026"}}',
            "scripts/digest-table.ts": _DIGEST_ARGS,
        },
        [("package.json", ['    "digest:weekly": "node scripts/digest-table.ts --year 2026 --with-muted"'])],
    ),
    (
        "trap-env-compose",
        [("OTTERLOG_CACHE_TTL", "docker-compose.yml")],
        "Raise `OTTERLOG_CACHE_TTL` (how many seconds otterlog caches entries, 30 by default) to 120 in "
        "docker-compose.yml; the upstream API is rate-limiting the status page.",
        "otterlog",
        {
            "package.json": '{"name": "otterlog", "scripts": {}}',
            "src/entries.ts": "const CACHE_MS = 30_000;\nexport const x = 1;\n",
            "docker-compose.yml": "services:\n  app:\n    build: .\n",
        },
        [("docker-compose.yml", ['      OTTERLOG_CACHE_TTL: "120"'])],
    ),
    (
        "trap-key-cfg",
        [("skip_muted_channels", "otterlog.cfg")],
        "Muted channels are getting archived. The archiver skips them when `skip_muted_channels = true` "
        "is set in otterlog.cfg's [archive] section: switch it on.",
        "otterlog",
        {
            "pyproject.toml": '[project]\nname = "otterlog"\n',
            "src/otterlog/__init__.py": "",
            "src/otterlog/config.py": (
                'import configparser\ncp = configparser.ConfigParser()\ncp.read("otterlog.cfg")\n'
                'batch = cp["archive"].getint("batch_size")\n'
            ),
            "otterlog.cfg": "[archive]\nbatch_size = 10\n",
        },
        [("otterlog.cfg", ["skip_muted_channels = true"])],
    ),
]


@pytest.mark.parametrize("case", PROBES, ids=[case[0] for case in PROBES])
def test_the_development_probes(tmp_path, case):
    _id, held, prompt, workspace, files, edits = case
    root, listed = _build(tmp_path / workspace, files)
    assert _dead(prompt, root, listed, edits) == held


# -- the rule's conditions ---------------------------------------------------------------------------
# (id, held, prompt, workspace directory, files, edits), on the otterlog repository unless stated.

CONDITIONS = [
    # Only the command's program owns a flag: after NAME=value assignments and launchers.
    (
        "flag-after-assignments-and-launchers",
        [("--totals", "scripts/nightly.sh")],
        TOTALS,
        "otterlog",
        BASE,
        [("scripts/nightly.sh", ["OTTERLOG_ENV=ci time node ./scripts/report.js --totals"])],
    ),
    (
        "flag-not-at-the-program-position",
        [],
        TOTALS,
        "otterlog",
        BASE,
        [("scripts/nightly.sh", ["echo scripts/report.js --totals"])],
    ),
    (
        "flag-to-an-npm-script",
        [("--totals", "scripts/nightly.sh")],
        TOTALS,
        "otterlog",
        {**BASE, "package.json": _NPM_REPORT},
        [("scripts/nightly.sh", ["npm run report -- --totals"])],
    ),
    (
        "flag-to-the-projects-command",
        [("--totals", "scripts/nightly.sh")],
        TOTALS,
        "otterlog",
        {**BASE, "pyproject.toml": _PY_COMMAND},
        [("scripts/nightly.sh", ["otterlog report --totals"])],
    ),
    (
        "flag-a-tools-own",
        [],
        "Pass `--inspect` to the nightly report so it can be debugged.",
        "otterlog",
        BASE,
        [("scripts/nightly.sh", ["node scripts/report.js --inspect"])],
    ),
    (
        "flag-handed-on-from-argv",
        [],
        TOTALS,
        "otterlog",
        {
            **BASE,
            "scripts/report.py": (
                "import subprocess, sys\nargs = sys.argv[1:]\nsubprocess.run(['pytest', *args])\n"
            ),
        },
        [("scripts/nightly.sh", ["python scripts/report.py --totals"])],
    ),
    (
        "flag-handed-on-by-a-bin-script",
        [],
        TOTALS,
        "otterlog",
        {**BASE, "bin/otterlog": '#!/bin/sh\nexec python -m otterlog "$@"\n'},
        [("scripts/nightly.sh", ["bin/otterlog report --totals"])],
    ),
    (
        "flag-read-by-a-same-edit-script-case-arm",
        [],
        TOTALS,
        "otterlog",
        BASE,
        [
            ("scripts/nightly.sh", ["node scripts/report.js --totals"]),
            ("bin/digest", ['case "$1" in', "  --totals) totals=1 ;;", "esac"]),
        ],
    ),
    # Env names: prefix reads, prefix options and the whole environment are reads.
    (
        "env-a-prefix-read",
        [],
        QUIET,
        "otterlog",
        {
            **BASE,
            "src/otterlog/flags.py": (
                'import os\n\n\ndef flag(key):\n    return os.environ.get(f"OTTERLOG_{key}")\n'
            ),
        },
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "env-a-prefix-option",
        [],
        QUIET,
        "otterlog",
        {
            **BASE,
            "src/otterlog/config.py": (
                "from pydantic_settings import BaseSettings, SettingsConfigDict\n\n\n"
                "class Config(BaseSettings):\n"
                '    model_config = SettingsConfigDict(env_prefix="OTTERLOG_")\n'
            ),
        },
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "env-the-whole-environment-to-a-child",
        [],
        QUIET,
        "otterlog",
        {**BASE, "src/otterlog/run.py": "import os, subprocess\n\nsubprocess.run(['w'], env=os.environ)\n"},
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "env-an-alias-read-by-literal-names-only",
        [("OTTERLOG_QUIET", ".env")],
        QUIET,
        "otterlog",
        {**BASE, "src/otterlog/port.py": "import os\n\nvals = os.environ\nPORT = vals['PORT']\n"},
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "env-the-edited-file-reads-it",
        [],
        QUIET,
        "otterlog",
        {**BASE, "scripts/deploy.sh": '#!/bin/sh\necho "quiet=$OTTERLOG_QUIET"\n'},
        [("scripts/deploy.sh", ["export OTTERLOG_QUIET=1"])],
    ),
    (
        "env-a-long-first-word-names-the-project",
        [("OTTER_QUIET", ".env")],
        "Set `OTTER_QUIET=1` in .env.",
        "otter-service",
        {"pyproject.toml": '[project]\nname = "otter-service"\n', "src/otter_service/__init__.py": ""},
        [(".env", ["OTTER_QUIET=1"])],
    ),
    (
        "env-a-short-first-word-does-not",
        [],
        "Set `KITE_QUIET=1` in .env.",
        "kite-service",
        {"pyproject.toml": '[project]\nname = "kite-service"\n', "src/kite_service/__init__.py": ""},
        [(".env", ["KITE_QUIET=1"])],
    ),
    # Readers: tests read switches too; a same-edit script only by a reader form.
    (
        "a-test-reads-it",
        [],
        QUIET,
        "otterlog",
        {
            **BASE,
            "tests/test_quiet.py": (
                "import os\n\n\ndef test_quiet():\n    assert os.environ.get('OTTERLOG_QUIET')\n"
            ),
        },
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "a-same-edit-test-reads-it",
        [],
        QUIET,
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"]), ("tests/test_quiet.py", ['assert os.environ["OTTERLOG_QUIET"]'])],
    ),
    (
        "a-same-edit-script-only-sets-it",
        [("OTTERLOG_QUIET", ".env"), ("OTTERLOG_QUIET", "scripts/deploy.sh")],
        QUIET,
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"]), ("scripts/deploy.sh", ["export OTTERLOG_QUIET=1"])],
    ),
    # Keys: a compound name, in a config file the code reads; never in pyproject.toml.
    (
        "key-a-plain-word-is-not-a-key",
        [],
        "Set `archive = true` in config/otterlog.toml.",
        "otterlog",
        {
            **BASE,
            "config/otterlog.toml": 'level = "info"\n',
            "src/otterlog/settings.py": _READS_CONFIG,
        },
        [("config/otterlog.toml", ["archive = true"])],
    ),
    (
        "key-not-in-pyproject",
        [],
        "Set `max_rows = 500` under `[tool.otterlog]` in pyproject.toml.",
        "otterlog",
        {
            **BASE,
            "pyproject.toml": '[project]\nname = "otterlog"\n\n[tool.otterlog]\nlevel = "info"\n',
            "src/otterlog/settings.py": (
                "import tomllib\nfrom pathlib import Path\n\n"
                "TOOL = tomllib.loads(Path('pyproject.toml').read_text())['tool']['otterlog']\n"
            ),
        },
        [("pyproject.toml", ["max_rows = 500"])],
    ),
    # What the request says: absence wording counts only when tied to the switch.
    (
        "absence-tied-to-the-switch",
        [],
        "`OTTERLOG_QUIET` isn't read anywhere yet; set it to 1 in .env anyway.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "a-symptom-word-is-not-absence",
        [("--totals", "scripts/nightly.sh")],
        "The staging export is missing the totals row: pass `--totals` to the nightly report.",
        "otterlog",
        BASE,
        [("scripts/nightly.sh", ["node scripts/report.js --totals"])],
    ),
    (
        "already-in-the-names-own-clause",
        [("OTTERLOG_QUIET", ".env")],
        "otterlog already honours `OTTERLOG_QUIET`; set it to 1 in .env.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "already-in-another-clause",
        [],
        "The banner already exists, so add a new `OTTERLOG_QUIET` variable and set it to 1 in .env.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "the-request-says-it-is-not-read-yet",
        [],
        "Switch the banner over to `OTTERLOG_QUIET` and set it to 1 in .env.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "the-request-says-we-dont-have-it",
        [],
        "We don't have a `OTTERLOG_QUIET` setting yet; set it to 1 in .env.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    (
        "the-next-sentence-asks-to-build-it",
        [],
        "Set `OTTERLOG_QUIET=1` in .env. Then implement it in the banner.",
        "otterlog",
        BASE,
        [(".env", ["OTTERLOG_QUIET=1"])],
    ),
    # Flags: a systemd ExecStart= program, and the project's command installed under a path.
    (
        "flag-to-a-systemd-execstart-command",
        [("--totals", "deploy/otterlog.service")],
        TOTALS,
        "otterlog",
        {**BASE, "pyproject.toml": _PY_COMMAND},
        [("deploy/otterlog.service", ["ExecStart=/opt/otterlog/venv/bin/otterlog report --totals"])],
    ),
    # Keys: the project must read another key of the section by name.
    (
        "key-a-sibling-read-through-the-named-section",
        [("quote_all", "otterlog.cfg")],
        "Set `quote_all = true` in the [export] section of otterlog.cfg.",
        "otterlog",
        {
            **BASE,
            "otterlog.cfg": "[export]\nsep = ;\n",
            "src/otterlog/export.py": (
                'import configparser\ncp = configparser.ConfigParser()\ncp.read("otterlog.cfg")\n'
                'SEP = cp["export"]["sep"]\n'
            ),
        },
        [("otterlog.cfg", ["quote_all = true"])],
    ),
    (
        "key-only-a-generic-sibling-is-read",
        [],
        "Set `archive_days = 30` in config/otterlog.toml.",
        "otterlog",
        {
            **BASE,
            "config/otterlog.toml": 'level = "info"\n',
            "src/otterlog/settings.py": _READS_CONFIG + "LEVEL = CONFIG['level']\n",
        },
        [("config/otterlog.toml", ["archive_days = 30"])],
    ),
    (
        "key-a-section-handed-to-a-library",
        [],
        "Set `disable_existing_loggers: false` in logging.json.",
        "otterlog",
        {
            **BASE,
            "logging.json": '{"version": 1, "handlers": {"console": {"class": "logging.StreamHandler"}}}\n',
            "src/otterlog/logs.py": (
                "import json\nimport logging.config\n\n"
                "logging.config.dictConfig(json.load(open('logging.json')))\n"
            ),
        },
        [("logging.json", ['  "disable_existing_loggers": false,'])],
    ),
    (
        "key-in-a-config-file-chosen-at-run-time",
        [("upload_timeout_s", "config/staging.json")],
        "Set `upload_timeout_s: 30` in config/staging.json.",
        "otterlog",
        {
            **BASE,
            "config/staging.json": '{"retry_limit": 3}\n',
            "src/otterlog/settings.py": (
                "import json, os\n\nENV = os.environ.get('OTTERLOG_ENV', 'dev')\n"
                "CFG = json.load(open(f'config/{ENV}.json'))\nLIMIT = CFG['retry_limit']\n"
            ),
        },
        [("config/staging.json", ['  "upload_timeout_s": 30,'])],
    ),
]


@pytest.mark.parametrize("case", CONDITIONS, ids=[case[0] for case in CONDITIONS])
def test_the_rules_conditions(tmp_path, case):
    _id, held, prompt, workspace, files, edits = case
    root, listed = _build(tmp_path / workspace, files)
    assert _dead(prompt, root, listed, edits) == held


# -- held: a request-named switch written into a place, where nothing reads it ------------------------


@pytest.mark.parametrize(
    "place, lines",
    [
        ("docker-compose.yml", ["      OTTERLOG_QUIET: '1'"]),
        (".env", ["OTTERLOG_QUIET=1"]),
        ("package.json", ['    "start": "OTTERLOG_QUIET=1 node scripts/report.js",']),
        ("deploy/k8s/app.yaml", ["        - name: OTTERLOG_QUIET", '          value: "1"']),
        ("Dockerfile", ["ENV OTTERLOG_QUIET=1"]),
        ("scripts/deploy.sh", ["export OTTERLOG_QUIET=1"]),
        ("deploy/otterlog.service", ["Environment=OTTERLOG_QUIET=1"]),
    ],
)
def test_a_project_env_switch_set_in_a_place_nothing_reads_is_held(tmp_path, place, lines):
    root, files = _repo(tmp_path)
    assert _dead(QUIET, root, files, [(place, lines)]) == [("OTTERLOG_QUIET", place)]


@pytest.mark.parametrize(
    "extra, place, line",
    [
        ({}, "scripts/nightly.sh", "node scripts/report.js --totals"),  # a repository file the line runs
        ({}, "Makefile", "\tpython -m otterlog.report --totals"),  # -m <own package>
        ({"pyproject.toml": _PY_COMMAND}, "scripts/nightly.sh", "otterlog report --totals"),  # own command
        (
            {"package.json": '{"name": "otterlog-web", "scripts": {"report": "node scripts/report.js"}}\n'},
            "scripts/nightly.sh",
            "npm run report --totals",  # an npm script whose command is one of those
        ),
    ],
    ids=["repository-file", "own-package", "own-command", "npm-script"],
)
def test_a_flag_passed_to_a_program_the_repository_owns_is_held(tmp_path, extra, place, line):
    root, files = _repo(tmp_path, extra)
    assert _dead(TOTALS, root, files, [(place, [line])]) == [("--totals", place)]


@pytest.mark.parametrize(
    "extra, prompt, place, line",
    [
        (
            {
                "config/otterlog.toml": 'level = "info"\nkeep_runs = 5\n',
                "src/otterlog/settings.py": _READS_CONFIG + "KEEP = CONFIG['keep_runs']\n",
            },
            "Set `archive_days = 30` in config/otterlog.toml so old runs are archived.",
            "config/otterlog.toml",
            "archive_days = 30",
        ),
        (
            {
                "data/rate-tiers/2026.json": '{"base": 100}\n',
                "src/otterlog/rates.py": (
                    "import json\nfrom pathlib import Path\n\nTIERS = Path('data/rate-tiers')\n\n\n"
                    "def base(year):\n    return json.loads((TIERS / f'{year}.json').read_text())['base']\n"
                ),
            },
            'Set `"surcharge_cap": 200` in data/rate-tiers/2026.json.',
            "data/rate-tiers/2026.json",
            '  "surcharge_cap": 200,',
        ),
    ],
    ids=["config-file-code-reads", "data-directory"],
)
def test_a_key_set_in_a_config_file_the_project_reads_is_held(tmp_path, extra, prompt, place, line):
    root, files = _repo(tmp_path, extra)
    key = prompt.split("`")[1].split("=")[0].split(":")[0].strip().strip('"')
    assert _dead(prompt, root, files, [(place, [line])]) == [(key, place)]


# -- silent -----------------------------------------------------------------------------------------


def test_a_switch_code_reads_is_not_held(tmp_path):
    root, files = _repo(
        tmp_path, {"src/otterlog/banner.py": "import os\n\nQUIET = os.environ.get('OTTERLOG_QUIET')\n"}
    )
    assert _dead(QUIET, root, files, [(".env", ["OTTERLOG_QUIET=1"])]) == []
    root2, files2 = _repo(
        tmp_path / "flag", {"scripts/report.js": "console.log(process.argv.includes('--totals'));\n"}
    )
    assert _dead(TOTALS, root2, files2, [("scripts/nightly.sh", ["node scripts/report.js --totals"])]) == []


def test_a_reader_the_same_patch_adds_means_it_is_being_built(tmp_path):
    root, files = _repo(tmp_path)
    edits = [
        (".env", ["OTTERLOG_QUIET=1"]),
        ("src/otterlog/banner.py", ['QUIET = os.environ.get("OTTERLOG_QUIET")']),
    ]
    assert _dead(QUIET, root, files, edits) == []
    assert _dead(QUIET, root, files, edits[:1]) == [("OTTERLOG_QUIET", ".env")]


@pytest.mark.parametrize(
    "prompt, place, line",
    [
        (
            "Set `strictChecks: true` in tsconfig.json.",
            "tsconfig.json",
            '  "strictChecks": true,',
        ),  # a tool's file
        ("Set `LOG_FORMAT=json` in .env.", ".env", "LOG_FORMAT=json"),  # not the project's prefix
        (TOTALS, "scripts/ci.sh", "pytest -q --totals"),  # another program's flag
        (
            TOTALS,
            "Dockerfile",
            "COPY scripts/report.js /app/report.js --totals",
        ),  # an instruction that runs nothing
        (
            "Add a new `OTTERLOG_QUIET` variable and set it to 1 in .env.",
            ".env",
            "OTTERLOG_QUIET=1",
        ),  # creation
        (
            "`OTTERLOG_QUIET` doesn't exist yet: set it to 1 in .env and read it in the app.",
            ".env",
            "OTTERLOG_QUIET=1",
        ),  # absence wording
        (QUIET, "README.md", "OTTERLOG_QUIET=1"),  # not a place
        (QUIET, "docker-compose.yml", '      - "${OTTERLOG_QUIET:-0}:1"'),  # an interpolation reads it
    ],
    ids=[
        "tool-owned-file",
        "unprefixed-env",
        "external-program",
        "dockerfile-copy",
        "creation",
        "absence",
        "doc",
        "interpolation",
    ],
)
def test_what_is_not_a_dead_switch(tmp_path, prompt, place, line):
    root, files = _repo(tmp_path)
    assert _dead(prompt, root, files, [(place, [line])]) == []


def test_a_program_that_forwards_its_arguments_is_not_the_flags_owner(tmp_path):
    forwarding = "import argparse\n\nargs, rest = argparse.ArgumentParser().parse_known_args()\n"
    root, files = _repo(tmp_path, {"scripts/report.py": forwarding})
    assert _dead(TOTALS, root, files, [("scripts/nightly.sh", ["python scripts/report.py --totals"])]) == []


def test_a_dependencys_env_name_is_not_the_projects(tmp_path):
    pyproject = '[project]\nname = "otterlog"\ndependencies = ["otterlog-client>=1"]\n'
    root, files = _repo(tmp_path, {"pyproject.toml": pyproject})
    assert _dead(QUIET, root, files, [(".env", ["OTTERLOG_QUIET=1"])]) == []


def test_a_name_already_noted_or_another_file_is_not_held(tmp_path):
    root, files = _repo(tmp_path)
    edits = [(".env", ["OTTERLOG_QUIET=1"])]
    assert _dead(QUIET, root, files, edits, skip={"OTTERLOG_QUIET"}) == []
    assert _dead(QUIET, root, files, edits, this_file="README.md") == []
    assert _dead(QUIET, root, files, edits, this_file=".env") == [("OTTERLOG_QUIET", ".env")]


def test_the_hold_text_names_the_absence(tmp_path):
    text = dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    assert names_absence(text, ["OTTERLOG_QUIET"])
    assert "`OTTERLOG_QUIET` doesn't exist in this codebase; nothing reads it" in text


def test_the_edits_lines_of_a_file_tool(tmp_path):
    root, _files = _repo(tmp_path, {"deploy/.env": "A=1\nB=2\n"})

    def event(tool: str, **arguments) -> AgentEvent:
        return AgentEvent(event=EventType.PRE_TOOL_USE, workspace=str(root), tool=tool, arguments=arguments)

    path = str(root / ".env")
    assert dead_switch.edited_lines(event("Write", file_path=path, content="A=1\nB=2\n"), root) == [
        (".env", ["A=1", "B=2"])
    ]
    # A Write rewrites the whole file: only the lines the file did not have are added.
    existing = str(root / "deploy/.env")
    assert dead_switch.edited_lines(event("Write", file_path=existing, content="B=2\nA=1\nC=3\n"), root) == [
        ("deploy/.env", ["C=3"])
    ]
    assert dead_switch.edited_lines(
        event("Edit", file_path=path, old_string="A=1\n", new_string="A=1\nC=3\n"), root
    ) == [(".env", ["C=3"])]
    edits = [{"old_string": "A=1", "new_string": "A=2"}, {"old_string": "B=2", "new_string": "B=2\nD=4"}]
    assert dead_switch.edited_lines(event("MultiEdit", file_path=path, edits=edits), root) == [
        (".env", ["A=2", "D=4"])
    ]
    assert dead_switch.edited_lines(event("Write", file_path="/elsewhere/x.env", content="A=1"), root) == []


# -- through the engine, rule D holding (``DEAD_SWITCH_SPEAKS`` True) --------------------------------


@pytest.fixture
def speaking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule D holding: the behaviour ported from the prototype."""
    monkeypatch.setattr(dead_switch, "DEAD_SWITCH_SPEAKS", True)


def _prompt(repo: Path, text: str, session: str = "s") -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": text,
    }


def _patch(repo: Path, body: str, session: str = "s") -> dict:
    return {
        "session_id": session,
        "turn_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": f"*** Begin Patch\n{body}*** End Patch\n"},
    }


def _add(path: str, *lines: str) -> str:
    return f"*** Add File: {path}\n" + "".join(f"+{line}\n" for line in lines)


def _update_with(path: str, context: str, *lines: str) -> str:
    return f"*** Update File: {path}\n@@\n {context}\n" + "".join(f"+{line}\n" for line in lines)


# A key in Codex's hook configuration (Level 0: self-protection asks the developer) and in the project's own
# config file, each in a section the project reads key by key.
_LEVEL_ZERO_REPO = {
    ".codex/config.toml": "keep_runs = 5\n",
    "config/otterlog.toml": "keep_runs = 5\n",
    "src/otterlog/settings.py": _READS_CONFIG + "KEEP = CONFIG['keep_runs']\n",
    "src/otterlog/hooks.py": "import tomllib\n\nHOOKS = tomllib.load(open('.codex/config.toml', 'rb'))\n",
}


def _denied(output: dict) -> str:
    """The deny's own text: without the closing line every Codex deny ends in (``test_day5_skill.py``)."""
    specific = output.get("hookSpecificOutput") or {}
    if specific.get("permissionDecision") != "deny":
        return ""
    return specific.get("permissionDecisionReason", "").removesuffix(f"\n\n{render.CLOSING}")


@pytest.fixture
def engine(tmp_path, speaking):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings())
    guard.workspace(root).index.ready(timeout=30)
    yield root, guard, lambda payload: translate.dispatch(guard, payload)
    guard.close()


def test_the_edit_is_held_once_with_the_premise_holds_kind_and_its_own_summary(engine):
    root, _guard, send = engine
    assert send(_prompt(root, QUIET))[0] == {}
    output, _results, decision = send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))
    assert _denied(output) == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    assert [f.subject for f in decision.findings] == ["false_premise"]
    assert decision.findings[0].summary == dead_switch.HOLD_SUMMARY
    assert decision.findings[0].detail == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}  # re-issued: proceeds
    assert send(_patch(root, _add("deploy/.env", "OTTERLOG_QUIET=1")))[0] == {}  # once per task


def test_a_new_task_can_be_held_again(engine):
    root, _guard, send = engine
    send(_prompt(root, QUIET))
    assert _denied(send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    send(_prompt(root, "Set `OTTERLOG_COLOR=0` in .env for the CI logs."))
    assert "OTTERLOG_COLOR" in _denied(send(_patch(root, _add(".env", "OTTERLOG_COLOR=0")))[0])


def test_a_codex_patch_is_read_whole_a_sibling_reader_counts(engine):
    root, _guard, send = engine
    send(_prompt(root, QUIET))
    reader = _add("src/otterlog/banner.py", "import os", 'QUIET = os.environ.get("OTTERLOG_QUIET")')
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1") + reader))[0] == {}
    unrelated = _add("src/otterlog/greet.py", "def greet():", "    return 'hi'")
    output, results, _decision = send(_patch(root, _add(".env", "OTTERLOG_QUIET=1") + unrelated))
    assert "nothing in this repository reads `OTTERLOG_QUIET`" in _denied(output)
    assert [event.tool for event, _d in results] == ["Write", "Write"]


def test_a_name_the_prompts_note_already_named_is_not_held_again(engine):
    root, _guard, send = engine
    ask = "otterlog already stays quiet when OTTERLOG_QUIET=1 is set; turn that on in .env."
    assert send(_prompt(root, ask))[0]["hookSpecificOutput"]["additionalContext"].startswith(
        "`OTTERLOG_QUIET`"
    )
    first = _denied(send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    assert first.startswith(
        "Truthstone: before editing: the request assumes `OTTERLOG_QUIET`"
    )  # the prompt's hold
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}  # not held again by rule D


def test_a_delete_is_not_held(engine):
    root, _guard, send = engine
    (root / ".env").write_text("OTTERLOG_QUIET=1\n")
    send(_prompt(root, QUIET))
    assert "OTTERLOG_QUIET" not in _denied(send(_patch(root, f"*** Delete File: {root / '.env'}\n"))[0])
    assert _denied(send(_patch(root, _add("deploy/.env", "OTTERLOG_QUIET=1")))[0])  # the task's first hold


def test_a_rule_that_fails_says_nothing(engine, monkeypatch):
    root, _guard, send = engine
    send(_prompt(root, QUIET))

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(dead_switch, "dead_switches", broken)
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}


def test_a_file_the_task_created_is_read_too(engine):
    """The readers are the indexed files and the task's touched files: a file the task created (a shell
    command's, say) that the index has not seen yet still reads the switch."""
    root, guard, send = engine
    send(_prompt(root, QUIET))
    (root / "src/otterlog/banner.py").write_text("import os\n\nQUIET = os.environ.get('OTTERLOG_QUIET')\n")
    ws = guard.workspace(root)
    assert "src/otterlog/banner.py" not in ws.index.files
    state = ws.task_state(ws.resolve_task_id("s"), "s")
    state.touched_files.add("src/otterlog/banner.py")
    assert send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0] == {}
    state.touched_files.discard("src/otterlog/banner.py")  # neither indexed nor touched: not read
    assert _denied(send(_patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])


@pytest.mark.usefixtures("speaking")
def test_level_zero_comes_first_and_the_hold_waits_for_the_next_edit(tmp_path):
    root, _files = _repo(tmp_path, _LEVEL_ZERO_REPO)
    guard = Guard(Settings())
    try:
        guard.workspace(root).index.ready(timeout=30)
        ask = "Set `archive_days = 30` in .codex/config.toml and in config/otterlog.toml."
        translate.dispatch(guard, _prompt(root, ask))
        hooks = _patch(root, _update_with(".codex/config.toml", "keep_runs = 5", "archive_days = 30"))
        first = _denied(translate.dispatch(guard, hooks)[0])
        assert first.startswith("needs developer sign-off")  # self-protection, not the hold
        config = _patch(root, _update_with("config/otterlog.toml", "keep_runs = 5", "archive_days = 30"))
        held = _denied(translate.dispatch(guard, config)[0])
        assert "nothing in this repository reads `archive_days`" in held
    finally:
        guard.close()


@pytest.mark.usefixtures("speaking")
@pytest.mark.parametrize("profile", ["minimal", "full"])
def test_it_speaks_wherever_the_premise_hold_speaks(tmp_path, profile):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(profile=profile))
    try:
        guard.workspace(root).index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        assert _denied(translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0])
    finally:
        guard.close()


@pytest.mark.usefixtures("speaking")
def test_observe_mode_withholds_it(tmp_path):
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(observe_only=True))
    try:
        guard.workspace(root).index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        output = translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0]
        assert output == {}
    finally:
        guard.close()


@pytest.mark.usefixtures("speaking")
def test_a_file_tools_write_is_held(tmp_path):
    root, _files = _repo(tmp_path, {"deploy/.env": "OTTERLOG_QUIET=1\n"})
    guard = Guard(Settings())
    try:
        guard.workspace(root).index.ready(timeout=30)
        prompt = AgentEvent(
            event=EventType.USER_PROMPT, workspace=str(root), session_id="c", prompt_text=QUIET
        )
        guard.handle(prompt)

        def write(rel: str, content: str) -> AgentEvent:
            arguments = {"file_path": str(root / rel), "content": content}
            return AgentEvent(
                event=EventType.PRE_TOOL_USE,
                workspace=str(root),
                session_id="c",
                tool="Write",
                arguments=arguments,
            )

        # A rewrite that keeps a line the file had sets nothing new.
        kept = guard.handle(write("deploy/.env", "OTTERLOG_LEVEL=debug\nOTTERLOG_QUIET=1\n"))
        assert kept.action.value == "allow"
        decision = guard.handle(write(".env", "OTTERLOG_QUIET=1\n"))
        assert decision.action.value == "challenge"
        assert decision.reason == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
    finally:
        guard.close()


@pytest.mark.usefixtures("speaking")
def test_a_hold_is_recorded_when_the_guard_defers_its_bookkeeping(tmp_path):
    """The daemon defers the advice; rule D is decided before it, so the hold the host sees is the decision
    stored, with its finding: what T4b and the bench's attestation read."""
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(profile="minimal"), defer_bookkeeping=True)
    try:
        ws = guard.workspace(root)
        ws.index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        output = translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0]
        assert _denied(output) == dead_switch.HOLD.format(name="OTTERLOG_QUIET", where="`.env`")
        with ws.event_lock:
            ws.drain()
        rows = ws.store.db.query(
            "SELECT d.action, d.reason FROM decisions d JOIN events e ON e.id = d.event_id "
            "WHERE d.project_id = ? AND e.type = 'pre_tool_use'",
            (ws.store.project_id,),
        )
        assert [list(row) for row in rows] == [["challenge", _denied(output)]]
        found = ws.store.db.query(
            "SELECT subject, summary FROM findings WHERE project_id = ?", (ws.store.project_id,)
        )
        assert [list(row) for row in found] == [["false_premise", dead_switch.HOLD_SUMMARY]]
    finally:
        guard.close()


# -- the shipped setting: rule D speaks (``DEAD_SWITCH_SPEAKS`` True since battery D2); the recorded-only mode
# below stays tested -----------------------------------------------------------------------------------------


def test_rule_d_ships_speaking():
    assert dead_switch.DEAD_SWITCH_SPEAKS is True


def _task_state(guard: Guard, root: Path, session: str = "s"):
    ws = guard.workspace(root)
    return ws.task_state(ws.resolve_task_id(session), session)


@pytest.mark.parametrize(
    "settings",
    [{"profile": "minimal"}, {"profile": "full"}, {"observe_only": True}],
    ids=["minimal", "full", "observe"],
)
def test_recorded_only_it_never_holds_and_keeps_the_hold_it_would_have_made(tmp_path, settings, monkeypatch):
    monkeypatch.setattr(dead_switch, "DEAD_SWITCH_SPEAKS", False)
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(**settings))
    try:
        guard.workspace(root).index.ready(timeout=30)
        translate.dispatch(guard, _prompt(root, QUIET))
        output, _results, decision = translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))
        assert output == {}
        assert all("premise" not in f.subject for f in decision.findings)
        assert _task_state(guard, root).dead_switch_recorded == [("OTTERLOG_QUIET", ".env")]
        translate.dispatch(guard, _patch(root, _add("deploy/.env", "OTTERLOG_QUIET=1")))
        assert _task_state(guard, root).dead_switch_recorded == [("OTTERLOG_QUIET", ".env")]  # once per task
        translate.dispatch(guard, _prompt(root, "Set `OTTERLOG_COLOR=0` in .env for the CI logs."))
        translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_COLOR=0")))
        assert _task_state(guard, root).dead_switch_recorded == [("OTTERLOG_COLOR", ".env")]  # a new task
    finally:
        guard.close()


def test_recorded_only_level_zero_still_comes_first(tmp_path, monkeypatch):
    monkeypatch.setattr(dead_switch, "DEAD_SWITCH_SPEAKS", False)
    root, _files = _repo(tmp_path, _LEVEL_ZERO_REPO)
    guard = Guard(Settings())
    try:
        guard.workspace(root).index.ready(timeout=30)
        ask = "Set `archive_days = 30` in .codex/config.toml and in config/otterlog.toml."
        translate.dispatch(guard, _prompt(root, ask))
        hooks = _patch(root, _update_with(".codex/config.toml", "keep_runs = 5", "archive_days = 30"))
        assert _denied(translate.dispatch(guard, hooks)[0]).startswith("needs developer sign-off")
        assert _task_state(guard, root).dead_switch_recorded == []  # the sign-off came first
        config = _patch(root, _update_with("config/otterlog.toml", "keep_runs = 5", "archive_days = 30"))
        assert translate.dispatch(guard, config)[0] == {}
        assert _task_state(guard, root).dead_switch_recorded == [("archive_days", "config/otterlog.toml")]
    finally:
        guard.close()


@pytest.mark.parametrize("speaks", [False, True], ids=["recorded-only", "holding"])
def test_what_the_bench_reads_of_a_session_whose_edit_rule_d_would_hold(tmp_path, monkeypatch, speaks):
    """T4b's ``_premise_flagged`` and T2's ``_blocked`` read a cell's stored decisions and findings (S9):
    recorded only, rule D leaves nothing for either; holding, its hold is a premise flag and a block."""
    monkeypatch.setattr(dead_switch, "DEAD_SWITCH_SPEAKS", speaks)
    root, _files = _repo(tmp_path)
    guard = Guard(Settings(profile="minimal"), defer_bookkeeping=True)  # the daemon's live path
    try:
        ws = guard.workspace(root)
        ws.index.ready(timeout=30)
        db = Path(ws.store.db.path)
        translate.dispatch(guard, _prompt(root, QUIET))
        output = translate.dispatch(guard, _patch(root, _add(".env", "OTTERLOG_QUIET=1")))[0]
        recorded = list(_task_state(guard, root).dead_switch_recorded)
    finally:
        guard.close()
    evidence = read_guard_db(db, root)
    cell_dir = tmp_path / "cell"
    cell_dir.mkdir()
    (cell_dir / "evidence.json").write_text(json.dumps(evidence.to_dict(), default=str))
    cell = {"_cell_dir": str(cell_dir), "evidence": evidence.summary()}
    assert bool(_denied(output)) is speaks
    assert acceptance._premise_flagged(cell) is speaks
    assert acceptance._blocked(cell) is speaks
    assert recorded == ([] if speaks else [("OTTERLOG_QUIET", ".env")])


# -- v4.1 (round 5, t2-5-1..4): quieter only -----------------------------------------------------------------


def _tree(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    root = tmp_path / name
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_v41_a_value_change_of_an_existing_key_is_not_a_new_switch(tmp_path):
    root = _tree(tmp_path, "farecard", {
        "package.json": '{"name": "farecard"}',
        "src/rates.ts": (
            'import card from "../data/cards/2026.json";\n'
            "export const z = (n: number) => card.zones[n];\n"
        ),
        "test/rates.test.ts": 'expect(card.zone_1).toBe(4);\n',
        "data/cards/2026.json": '{\n  "zone_1": 4,\n  "zone_3": 5\n}\n',
    })
    files = ["package.json", "src/rates.ts", "test/rates.test.ts", "data/cards/2026.json"]
    prompt = "Raise `zone_3` to 6 in data/cards/2026.json."
    assert dead_switch.dead_switches(prompt, root, files, [("data/cards/2026.json", ['  "zone_3": 6'])]) == []


def test_v41_an_existing_word_far_from_the_name_does_not_cancel_a_creation_request(tmp_path):
    root = _tree(tmp_path, "importly", {
        "pyproject.toml": '[project]\nname = "importly"\n',
        "src/importly/__init__.py": "",
        "src/importly/config.py": (
            'import tomllib\nCFG = tomllib.load(open("importly.toml", "rb"))\n'
            'B = CFG["batch"]["batch_size"]\n'
        ),
        "importly.toml": "[batch]\nbatch_size = 10\n",
    })
    files = ["pyproject.toml", "src/importly/__init__.py", "src/importly/config.py", "importly.toml"]
    prompt = (
        "The importer currently reads `batch_size` from importly.toml "
        "and we need a `max_retries` key there too."
    )
    assert dead_switch.dead_switches(prompt, root, files, [("importly.toml", ["max_retries = 3"])]) == []


def test_v41_only_a_scanned_file_owns_a_program(tmp_path):
    root = _tree(tmp_path, "shipdesk", {
        "package.json": '{"name": "shipdesk", "scripts": {"pages": "node build/gen.js"}}',
        "build/gen.js": "console.log(process.argv);\n",
    })
    prompt = "gen.js prints the Remote row when run with --with-remote: switch that on in the pages script."
    edits = [("package.json", ['    "pages": "node build/gen.js --with-remote"'])]
    assert dead_switch.dead_switches(prompt, root, ["package.json"], edits) == []


def test_v41_a_compose_interpolation_reads_an_env_name(tmp_path):
    root = _tree(tmp_path, "tidemark", {
        "package.json": '{"name": "tidemark"}',
        "src/server.ts": "export const port = 8080;\n",
        "docker-compose.yml": (
            "services:\n  app:\n    build: .\n"
            "    command: node dist/server.js --cache ${TIDEMARK_CACHE_TTL}\n"
        ),
        ".env": "TIDEMARK_REGION=eu\n",
    })
    files = ["package.json", "src/server.ts", "docker-compose.yml", ".env"]
    prompt = "Set `TIDEMARK_CACHE_TTL=120` in .env."
    assert dead_switch.dead_switches(prompt, root, files, [(".env", ["TIDEMARK_CACHE_TTL=120"])]) == []
