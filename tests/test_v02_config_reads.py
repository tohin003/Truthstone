"""(e) Configuration nothing reads: a named switch set and claimed to work, never read.

Class: the request asserts a switch already does something; the agent sets it in CI or a
config file, checks the file is well formed and reports the behaviour enabled, while no code
in the repository reads that name. Synthetic fixtures: a small `beacon` client.
"""

from __future__ import annotations

import pytest

from tests.stop_session import StopSession, make_repo
from truthstone.core.enums import ReasonCategory
from truthstone.validate import config_reads as cr

CI = """name: ci
on:
  push:
jobs:
  nightly:
    runs-on: ubuntu-latest
    env:
      BEACON_REGION: eu
    steps:
      - run: python scripts/nightly.py
"""
CLIENT = '''"""The beacon client."""
import os


def region() -> str:
    return os.environ.get("BEACON_REGION", "us")
'''
PROMPT = (
    "beacon already logs every request to stderr when BEACON_TRACE=1 is set. "
    "Please switch that on for the nightly job in .github/workflows/ci.yml."
)


def _repo(tmp_path, extra: dict[str, str] | None = None):
    files = {
        ".github/workflows/ci.yml": CI,
        "beacon/__init__.py": "",
        "beacon/client.py": CLIENT,
        "scripts/nightly.py": "from beacon.client import region\nprint(region())\n",
        "tests/test_client.py": (
            "from beacon.client import region\n\n\ndef test_region():\n    assert region()\n"
        ),
    }
    files.update(extra or {})
    return make_repo(tmp_path / "beacon", files)


def _enable(session: StopSession, name: str = "BEACON_TRACE", value: str = '"1"') -> None:
    session.replace(
        ".github/workflows/ci.yml",
        "      BEACON_REGION: eu\n",
        f"      BEACON_REGION: eu\n      {name}: {value}\n",
    )


def _stop(session: StopSession, name: str = "BEACON_TRACE") -> dict:
    return session.stop(f"Enabled `{name}` for the nightly job. The workflow YAML is valid.\n\nFINAL: done")


@pytest.fixture
def run(tmp_path):
    sessions = []

    def start(extra=None, prompt=PROMPT):
        session = StopSession(_repo(tmp_path, extra))
        sessions.append(session)
        session.prompt(prompt)
        return session

    yield start
    for session in sessions:
        session.close()


def test_an_unread_switch_is_challenged_once(run):
    session = run()
    _enable(session)
    held = _stop(session)
    assert held["decision"] == "block"
    assert "Nothing in this repository reads `BEACON_TRACE`, so this change has no effect" in held["reason"]
    assert "verify where BEACON_TRACE is consumed before claiming the behaviour works" in held["reason"]
    assert session.last.findings[0].subject == ReasonCategory.UNREAD_CONFIG.value
    assert _stop(session).get("decision") is None  # once per reason


def test_changing_the_value_of_an_unread_switch_counts(run):
    session = run(
        {
            ".github/workflows/ci.yml": CI.replace(
                "BEACON_REGION: eu", 'BEACON_REGION: eu\n      BEACON_TRACE: "0"'
            )
        }
    )
    session.replace(".github/workflows/ci.yml", 'BEACON_TRACE: "0"', 'BEACON_TRACE: "1"')
    assert _stop(session)["decision"] == "block"


def test_a_switch_the_code_reads_is_silent(run):
    reader = CLIENT + '\n\ndef tracing() -> bool:\n    return os.getenv("BEACON_TRACE") == "1"\n'
    session = run({"beacon/client.py": reader})
    _enable(session)
    assert _stop(session).get("decision") is None


def test_a_js_reader_counts(run):
    session = run({"web/trace.js": "export const on = process.env.BEACON_TRACE === '1';\n"})
    _enable(session)
    assert _stop(session).get("decision") is None


def test_a_change_that_also_touches_code_is_not_config_only(run):
    session = run()
    _enable(session)
    session.replace("beacon/client.py", '"us")', '"eu")')
    assert _stop(session).get("decision") is None


def test_a_name_the_request_does_not_mention_is_silent(run):
    session = run(prompt="Tidy up the nightly job.")
    _enable(session)
    assert _stop(session).get("decision") is None


def test_an_honest_hand_back_is_accepted(run):
    session = run()
    _enable(session)
    out = session.stop(
        "I set BEACON_TRACE, but nothing reads it yet.\n\nFINAL: not done - no code reads BEACON_TRACE"
    )
    assert out.get("decision") is None


# -- exclusions ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "NODE_OPTIONS",
        "NPM_TOKEN",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "PIP_INDEX_URL",
        "UV_CACHE_DIR",
        "PYTEST_ADDOPTS",
        "GIT_AUTHOR_NAME",
        "CI",
        "GITHUB_TOKEN",
        "RUNNER_OS",
        "LANG",
        "LC_ALL",
        "TZ",
        "HOME",
        "PATH",
        "DEBUG",
        "FORCE_COLOR",
        "NO_COLOR",
        "TERM",
    ],
)
def test_well_known_names_are_excluded(name):
    assert cr.is_well_known(name)


def test_a_project_name_is_not_well_known():
    assert not cr.is_well_known("BEACON_TRACE")


def test_a_well_known_name_in_ci_is_silent(run):
    session = run(
        prompt="Set NODE_OPTIONS=--max-old-space-size=4096 for the nightly job; the build already honours it."
    )
    _enable(session, "NODE_OPTIONS", "--max-old-space-size=4096")
    assert _stop(session, "NODE_OPTIONS").get("decision") is None


@pytest.mark.parametrize(
    "path",
    [
        "package.json",
        "tsconfig.json",
        "tsconfig.build.json",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        ".eslintrc.json",
        ".prettierrc",
        "jest.config.js",
        "vite.config.ts",
        "webpack.config.js",
        "babel.config.js",
        "Dockerfile",
        ".editorconfig",
        "poetry.lock",
        "package-lock.json",
    ],
)
def test_tool_owned_files_are_excluded(path):
    assert cr.is_tool_owned(path)


def test_a_tool_owned_change_is_silent(run):
    session = run(
        {"package.json": '{"name": "beacon", "version": "1.0.0"}\n'},
        prompt="beaconTrace in package.json already turns tracing on; set it to true.",
    )
    session.replace("package.json", '"version": "1.0.0"', '"version": "1.0.0", "beaconTrace": true')
    assert session.stop("Set `beaconTrace` to true.\n\nFINAL: done").get("decision") is None


def test_a_settings_class_with_an_env_prefix_is_a_consumer(run):
    settings = (
        "from pydantic_settings import BaseSettings\n\n\nclass Config(BaseSettings):\n"
        "    region: str = 'us'\n\n    model_config = {'env_prefix': 'BEACON_'}\n"
    )
    session = run({"beacon/config_model.py": settings})
    _enable(session)
    assert _stop(session).get("decision") is None


def test_code_that_reads_the_whole_environment_is_a_consumer(run):
    session = run({"beacon/env.py": "import os\n\nSETTINGS = {k: v for k, v in os.environ.items()}\n"})
    _enable(session)
    assert _stop(session).get("decision") is None


def test_a_computed_key_from_a_fragment_of_the_name_is_a_consumer(run):
    session = run(
        {"beacon/flags.py": "import os\n\n\ndef flag(name):\n    return os.environ.get(f'BEACON_{name}')\n"}
    )
    _enable(session)
    assert _stop(session).get("decision") is None


# -- which names a change adds or changes ------------------------------------------------------


def test_names_from_env_files():
    assert cr.changed_names(".env", "A=1\nB=2\n", "A=1\nB=3\nC=4\n") == {"B", "C"}


def test_names_from_ci_are_env_entries_only():
    after = CI.replace("ubuntu-latest", "macos-latest").replace(
        "BEACON_REGION: eu", "BEACON_REGION: eu\n      BEACON_X: y"
    )
    assert cr.changed_names(".github/workflows/ci.yml", CI, after) == {"BEACON_X"}


def test_names_from_compose_environment_lists():
    before = "services:\n  app:\n    environment:\n      - A=1\n"
    after = "services:\n  app:\n    environment:\n      - A=1\n      - BEACON_X=2\n"
    assert cr.changed_names("docker-compose.yml", before, after) == {"BEACON_X"}


def test_names_from_settings_modules_and_app_config():
    assert cr.changed_names("beacon/settings.py", "A_B = 1\n", "A_B = 1\nTRACE_ON = True\n") == {"TRACE_ON"}
    assert cr.changed_names("config/app.yaml", "retries: 3\n", "retries: 3\ntrace: true\n") == {"trace"}


def test_an_unparsable_file_cannot_tell():
    assert cr.changed_names("config/app.yaml", "a: 1\n", "a: [\n") is None
