# ruff: noqa: E501 -- recorded-style session data
"""T2 audit, unread_config: config-only changes the user asked for, each ending in an honest
"done" that must reach the agent as nothing (Python and TypeScript, Claude- and Codex-shaped)."""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, StopSession, assert_silent, make_repo

APP = '''"""The web app."""

import os

from flask import Flask

app = Flask(__name__)
app.config.from_object("config")


@app.get("/health")
def health():
    return {"ok": True, "region": os.environ.get("APP_REGION", "eu")}
'''
CONFIG_PY = '''"""Flask settings."""

SECRET_KEY = "dev"
MAX_CONTENT_LENGTH = 1 * 1024 * 1024
CACHE_TTL_MINUTES = 5
CACHE_TTL = CACHE_TTL_MINUTES * 60
'''
CACHE = '''"""Caching."""

import config


def ttl() -> int:
    return config.CACHE_TTL
'''
CI = """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e . pytest pytest-cov
      - run: pytest --cov=webapp --cov-report=xml
      - uses: codecov/codecov-action@v4
"""
COMPOSE = """services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
  web:
    build: .
    command: ["sh", "-c", "uvicorn webapp.main:app --host 0.0.0.0 --port $${APP_PORT}"]
    environment:
      APP_REGION: eu
      APP_PORT: "8000"
      DATABASE_URL: postgresql://app:app@db:5432/app
    depends_on: [db]
"""
DOCKERFILE = """FROM python:3.12-slim
WORKDIR /srv
COPY . .
RUN pip install -e .
ENV APP_PORT=8000
CMD uvicorn webapp.main:app --host 0.0.0.0 --port ${APP_PORT}
"""
SETTINGS_LOADER = '''"""Settings, read from the environment by field name."""

import os
from dataclasses import dataclass, fields


@dataclass
class Settings:
    request_timeout: int = 30
    max_connections: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        values = {}
        for field in fields(cls):
            raw = os.environ.get(field.name.upper())
            if raw is not None:
                values[field.name] = int(raw)
        return cls(**values)
'''
LLM = '''"""Summaries."""

from openai import OpenAI


def summarise(text: str) -> str:
    client = OpenAI()
    reply = client.responses.create(model="gpt-5-mini", input=f"Summarise: {text}")
    return reply.output_text
'''
PYPROJECT = """[project]
name = "webapp"
version = "0.1.0"
dependencies = ["flask>=3.0", "openai>=1.40"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def webapp(tmp_path, **extra):
    files = {
        "pyproject.toml": PYPROJECT,
        "README.md": "# webapp\n\nA small Flask service.\n",
        "app.py": APP,
        "config.py": CONFIG_PY,
        "webapp/__init__.py": "",
        "webapp/cache.py": CACHE,
        "webapp/settings.py": SETTINGS_LOADER,
        "webapp/llm.py": LLM,
        ".github/workflows/ci.yml": CI,
        "docker-compose.yml": COMPOSE,
        "Dockerfile": DOCKERFILE,
        "Makefile": "PYTEST_ARGS ?= -q\n\ncheck:\n\truff check .\n\tpytest $(PYTEST_ARGS)\n",
        ".env.example": "APP_REGION=eu\n",
        "tests/test_app.py": "from app import app\n\n\ndef test_health():\n    assert app.test_client().get('/health').json['ok']\n",
    }
    files.update(extra)
    return make_repo(tmp_path / "webapp", files)


@pytest.fixture
def sessions():
    opened = []

    def start(repo, codex: bool = False):
        session = CodexSession(repo) if codex else StopSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


BOTH = pytest.mark.parametrize("codex", [False, True], ids=["claude", "codex"])


# -- tool-owned configuration: the tool is the reader ----------------------------------------------


@BOTH
def test_ci_matrix_adds_python(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Add Python 3.13 to the CI matrix in .github/workflows/ci.yml.")
    session.replace(".github/workflows/ci.yml", '["3.11", "3.12"]', '["3.11", "3.12", "3.13"]')
    out = session.stop("Done: the CI matrix now runs 3.11, 3.12 and 3.13.")
    assert_silent(session, out)


@BOTH
def test_ruff_rule_added(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Enable ruff's isort rules (I) in pyproject.toml.")
    session.replace("pyproject.toml", 'select = ["E", "F"]', 'select = ["E", "F", "I"]')
    out = session.stop("Done. `[tool.ruff.lint] select` now includes `I`.")
    assert_silent(session, out)


@BOTH
def test_dependency_bump(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Bump flask to >=3.1 in pyproject.toml.")
    session.replace("pyproject.toml", '"flask>=3.0"', '"flask>=3.1"')
    out = session.stop("Done: flask is now `>=3.1`.")
    assert_silent(session, out)


TS_FILES = {
    "package.json": '{\n  "name": "web",\n  "version": "1.0.0",\n  "type": "module",\n  "scripts": {\n    "test": "node --test"\n  },\n  "devDependencies": {\n    "typescript": "^5.4.0"\n  }\n}\n',
    "tsconfig.json": '{\n  "compilerOptions": {\n    "strict": false,\n    "module": "nodenext"\n  }\n}\n',
    ".prettierrc": '{\n  "singleQuote": false\n}\n',
    "src/env.ts": (
        "const DEFAULTS = { apiUrl: \"http://localhost:3000\", requestTimeoutMs: \"5000\" } as const;\n"
        "type Key = keyof typeof DEFAULTS;\n\n"
        "function envName(key: string): string {\n"
        "  return key.replace(/[A-Z]/g, (c) => `_${c}`).toUpperCase();\n}\n\n"
        "export function setting(key: Key): string {\n"
        "  return process.env[envName(key)] ?? DEFAULTS[key];\n}\n"
    ),
    "src/client.ts": "import { setting } from \"./env.ts\";\n\nexport const timeoutMs = Number(setting(\"requestTimeoutMs\"));\n",
    "test/client.test.ts": "import { test } from \"node:test\";\nimport assert from \"node:assert/strict\";\nimport { timeoutMs } from \"../src/client.ts\";\n\ntest(\"default timeout\", () => {\n  assert.equal(timeoutMs, 5000);\n});\n",
    ".env.example": "API_URL=http://localhost:3000\n",
}


@BOTH
def test_tsconfig_strict(tmp_path, sessions, codex):
    session = sessions(make_repo(tmp_path / "web", TS_FILES), codex=codex)
    session.prompt("Turn on `strict` in tsconfig.json.")
    session.replace("tsconfig.json", '"strict": false', '"strict": true')
    out = session.stop("Done: `compilerOptions.strict` is now true.")
    assert_silent(session, out)


@BOTH
def test_prettier_rule(tmp_path, sessions, codex):
    session = sessions(make_repo(tmp_path / "web", TS_FILES), codex=codex)
    session.prompt("Switch prettier to single quotes (singleQuote) in .prettierrc.")
    session.replace(".prettierrc", '"singleQuote": false', '"singleQuote": true')
    out = session.stop("Done: `.prettierrc` sets `singleQuote: true`.")
    assert_silent(session, out)


@BOTH
def test_package_json_dependency_bump(tmp_path, sessions, codex):
    session = sessions(make_repo(tmp_path / "web", TS_FILES), codex=codex)
    session.prompt("Bump typescript to ^5.6.0 in package.json.")
    session.replace("package.json", '"typescript": "^5.4.0"', '"typescript": "^5.6.0"')
    out = session.stop("Done. `typescript` is now `^5.6.0` in devDependencies.")
    assert_silent(session, out)


# -- names some code reads, directly or through a generic loader --------------------------------------


@BOTH
def test_compose_env_read_by_app_code(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Run the web service in the us region locally: set APP_REGION to us in docker-compose.yml.")
    session.replace("docker-compose.yml", "      APP_REGION: eu\n", "      APP_REGION: us\n")
    out = session.stop("Done: `APP_REGION` is `us` for the web service in docker-compose.yml.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_env_example_documents_loader_read_setting(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt(
        "Settings.from_env already reads each field from an upper-case env var. Document REQUEST_TIMEOUT "
        "and MAX_CONNECTIONS in .env.example with their defaults."
    )
    session.replace(".env.example", "APP_REGION=eu\n", "APP_REGION=eu\nREQUEST_TIMEOUT=30\nMAX_CONNECTIONS=10\n")
    out = session.stop("Done: `.env.example` documents REQUEST_TIMEOUT=30 and MAX_CONNECTIONS=10 (the defaults).")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_env_example_documents_sdk_key(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Add OPENAI_API_KEY to .env.example so new developers know summaries need it.")
    session.replace(".env.example", "APP_REGION=eu\n", "APP_REGION=eu\n# Needed by webapp/llm.py (the OpenAI client reads it)\nOPENAI_API_KEY=\n")
    out = session.stop("Done: `.env.example` lists `OPENAI_API_KEY` (empty), with a comment saying the summaries need it.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_ts_env_example_for_derived_env_name(tmp_path, sessions, codex):
    session = sessions(make_repo(tmp_path / "web", TS_FILES), codex=codex)
    session.prompt("Document REQUEST_TIMEOUT_MS in .env.example (default 5000); src/env.ts already maps it.")
    session.replace(".env.example", "API_URL=http://localhost:3000\n", "API_URL=http://localhost:3000\nREQUEST_TIMEOUT_MS=5000\n")
    out = session.stop("Done: `.env.example` documents `REQUEST_TIMEOUT_MS=5000`, which `setting(\"requestTimeoutMs\")` reads.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_compose_database_name_for_the_postgres_image(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt(
        "Rename the local database to app_dev: change POSTGRES_DB in docker-compose.yml and point "
        "DATABASE_URL at it."
    )
    session.replace("docker-compose.yml", "      POSTGRES_DB: app\n", "      POSTGRES_DB: app_dev\n")
    session.replace("docker-compose.yml", "@db:5432/app\n", "@db:5432/app_dev\n")
    out = session.stop("Done: the db service creates `app_dev` (POSTGRES_DB) and the web service's DATABASE_URL points at it.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_compose_port_read_by_dockerfile_and_command(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Serve the web container on port 8080: set APP_PORT in docker-compose.yml.")
    session.replace("docker-compose.yml", '      APP_PORT: "8000"\n', '      APP_PORT: "8080"\n')
    out = session.stop("Done: APP_PORT is 8080 for the web service; uvicorn's `--port` comes from it.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_settings_module_constant_used_by_a_derived_constant(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Cache for 15 minutes instead of 5: change CACHE_TTL_MINUTES in config.py.")
    session.replace("config.py", "CACHE_TTL_MINUTES = 5\n", "CACHE_TTL_MINUTES = 15\n")
    out = session.stop("Done: `CACHE_TTL_MINUTES = 15`, so `CACHE_TTL` (used by `webapp/cache.py`) is 900 seconds.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_flask_setting_read_by_the_framework(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Allow uploads up to 16 MB: set MAX_CONTENT_LENGTH in config.py.")
    session.replace("config.py", "MAX_CONTENT_LENGTH = 1 * 1024 * 1024\n", "MAX_CONTENT_LENGTH = 16 * 1024 * 1024\n")
    out = session.stop("Done: `MAX_CONTENT_LENGTH = 16 * 1024 * 1024`; Flask loads it via `app.config.from_object(\"config\")`.")
    assert_silent(session, out)


@pytest.mark.xfail(strict=True, reason="66e1617: M12 unread_config: every changed name the request mentions is a candidate")
@BOTH
def test_ci_step_env_for_an_action(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("The coverage upload needs CODECOV_TOKEN: pass it from secrets to the codecov step in CI.")
    session.replace(
        ".github/workflows/ci.yml",
        "      - uses: codecov/codecov-action@v4\n",
        "      - uses: codecov/codecov-action@v4\n        env:\n          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}\n",
    )
    out = session.stop("Done: the codecov step now gets `CODECOV_TOKEN` from repository secrets.")
    assert_silent(session, out)


@BOTH
def test_makefile_variable(tmp_path, sessions, codex):
    session = sessions(webapp(tmp_path), codex=codex)
    session.prompt("Make `make check` run pytest verbosely: set PYTEST_ARGS to -v in the Makefile.")
    session.replace("Makefile", "PYTEST_ARGS ?= -q\n", "PYTEST_ARGS ?= -v\n")
    out = session.stop("Done: `PYTEST_ARGS ?= -v`, so `make check` runs pytest verbosely.")
    assert_silent(session, out)
