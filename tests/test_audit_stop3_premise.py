# ruff: noqa: E501
"""T2 audit, round 3: premise prompts about web and data things (routes, endpoints, tables,
columns, fields, OpenAPI operations, template variables, env names) and src-layout or monorepo
paths. Every name the prompt leans on exists in the repository, so there must be no premise note,
and the first edit after the prompt must not be held."""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.adapters.codex import translate
from truthstone.core.config import Settings
from truthstone.core.engine import Guard

Q4 = pytest.mark.xfail(strict=True, reason="66e1617: R3-4 a name the prompt says is absent ('ignores', 'has no', 'lacks') is noted and held")


@pytest.fixture(autouse=True)
def _product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUTHSTONE_PROFILE", raising=False)


WEB_PY = {
    "pyproject.toml": '[project]\nname = "stockroom"\nversion = "0.2.0"\ndependencies = ["flask>=3"]\n\n[tool.pytest.ini_options]\npythonpath = ["src"]\n',
    "README.md": "# stockroom\n\nA small inventory service.\n",
    "src/stockroom/__init__.py": "",
    "src/stockroom/app.py": (
        "from flask import Flask, jsonify\n\nfrom stockroom.db import list_items\n\napp = Flask(__name__)\n\n\n"
        '@app.get("/health")\ndef health():\n    return jsonify(status="ok"), 200\n\n\n'
        '@app.get("/api/items")\ndef items():\n    return jsonify(list_items())\n'
    ),
    "src/stockroom/db.py": (
        "import os\nimport sqlite3\n\nDB_PATH = os.environ.get(\"STOCKROOM_DB\", \"stock.db\")\n\n\n"
        "def list_items():\n    with sqlite3.connect(DB_PATH) as conn:\n"
        '        return [dict(zip(("id", "name", "created_at"), row)) for row in conn.execute("SELECT id, name, created_at FROM items")]\n'
    ),
    "src/stockroom/models.py": (
        "from dataclasses import dataclass\nfrom datetime import datetime\n\n\n@dataclass\nclass Item:\n    id: int\n    name: str\n    created_at: datetime\n"
    ),
    "migrations/001_init.sql": (
        "CREATE TABLE users (\n    id INTEGER PRIMARY KEY,\n    email TEXT NOT NULL,\n    display_name TEXT\n);\n\n"
        "CREATE TABLE items (\n    id INTEGER PRIMARY KEY,\n    name TEXT NOT NULL,\n    owner_id INTEGER REFERENCES users(id),\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);\n"
    ),
    "openapi.yaml": (
        "openapi: 3.0.3\ninfo:\n  title: stockroom\n  version: 0.2.0\npaths:\n  /api/items:\n    get:\n      operationId: listItems\n"
        "      responses:\n        '200':\n          description: OK\n          content:\n            application/json:\n              schema:\n"
        "                type: array\n                items:\n                  $ref: '#/components/schemas/ItemSummary'\n"
        "components:\n  schemas:\n    ItemSummary:\n      type: object\n      properties:\n        id: {type: integer}\n        name: {type: string}\n        createdAt: {type: string, format: date-time}\n"
    ),
    "src/stockroom/templates/receipt.html": "<h1>Receipt for {{ customer_name }}</h1>\n<p>Total: {{ total_display }}</p>\n",
    "tests/test_app.py": "from stockroom.app import app\n\n\ndef test_health():\n    assert app.test_client().get('/health').status_code == 200\n",
    ".env.example": "STOCKROOM_DB=stock.db\n",
}

PY_PROMPTS = [
    "The `/health` endpoint already returns 200 — add a `/ready` endpoint that also checks the database.",
    "The `users` table has an `email` column; add an index on it in a new migration.",
    "The existing `GET /api/items` route returns everything. Add `?limit=` and `?offset=` paging to it.",
    "The `created_at` field on items should be returned as ISO-8601 in the `/api/items` response.",
    "Add a `owner_id` filter to `listItems` in openapi.yaml and implement it in src/stockroom/app.py.",
    "The `ItemSummary` schema in openapi.yaml is missing `owner_id`. Add it, and return it from the route.",
    "In src/stockroom/templates/receipt.html, `{{ customer_name }}` should fall back to 'Guest' when empty.",
    "`STOCKROOM_DB` is read in src/stockroom/db.py; document it in the README.",
    "Rename the `display_name` column on `users` to `full_name` with a new migration.",
    "Add a `DELETE /api/items/<id>` route next to the existing `GET /api/items` one.",
    "`list_items` in src/stockroom/db.py opens a new connection per call. Make it reuse one connection.",
    "The `/api/items` endpoint should sort by `created_at` descending.",
    "Add an `updated_at` column to the `items` table and set it on every update.",
    "The `items.owner_id` foreign key needs `ON DELETE CASCADE`. Write the migration.",
    "Write a test for the `/health` route in tests/test_app.py that checks the JSON body is {\"status\": \"ok\"}.",
]

WEB_TS = {
    "package.json": '{\n  "name": "shelfy",\n  "private": true,\n  "workspaces": ["packages/*"]\n}\n',
    "packages/api/package.json": '{\n  "name": "@shelfy/api",\n  "version": "0.3.0",\n  "scripts": {"test": "vitest run"}\n}\n',
    "packages/api/src/server.ts": (
        'import express from "express";\nimport { listOrders } from "./orders";\n\nexport const app = express();\n\n'
        'app.get("/health", (_req, res) => res.status(200).json({ ok: true }));\n'
        'app.get("/api/orders", async (req, res) => res.json(await listOrders(Number(req.query.limit ?? 20))));\n'
        'app.use((req, res, next) => { res.setHeader("X-Request-Id", req.get("X-Request-Id") ?? crypto.randomUUID()); next(); });\n'
    ),
    "packages/api/src/orders.ts": (
        'import { db } from "./db";\n\nexport interface Order {\n  id: number;\n  totalCents: number;\n  createdAt: Date;\n}\n\n'
        "export async function listOrders(limit: number): Promise<Order[]> {\n"
        '  return db.query("SELECT id, total_cents AS \\"totalCents\\", created_at AS \\"createdAt\\" FROM orders LIMIT $1", [limit]);\n}\n'
    ),
    "packages/api/src/db.ts": 'import { Pool } from "pg";\n\nexport const db = new Pool({ connectionString: process.env.DATABASE_URL });\n',
    "packages/api/test/orders.test.ts": 'import { expect, test } from "vitest";\n\ntest("placeholder", () => expect(1).toBe(1));\n',
    "packages/api/prisma/schema.prisma": "model Order {\n  id         Int      @id @default(autoincrement())\n  totalCents Int      @map(\"total_cents\")\n  createdAt  DateTime @default(now()) @map(\"created_at\")\n\n  @@map(\"orders\")\n}\n",
    "packages/web/package.json": '{\n  "name": "@shelfy/web",\n  "version": "0.3.0"\n}\n',
    "packages/web/src/api.ts": 'export async function fetchOrders() {\n  const res = await fetch("/api/orders?limit=20");\n  return res.json();\n}\n',
}

TS_PROMPTS = [
    "The `/health` endpoint in packages/api/src/server.ts already returns 200 — add `/ready`.",
    "The `orders` table has a `created_at` column; add an index on it via a Prisma migration.",
    "The existing `GET /api/orders` route ignores `offset`. Add offset paging in packages/api/src/server.ts and packages/api/src/orders.ts.",
    "`listOrders` in packages/api/src/orders.ts should order by `createdAt` descending.",
    "The `X-Request-Id` header is set in packages/api/src/server.ts; log it on every request too.",
    "`DATABASE_URL` is read in packages/api/src/db.ts. Make it fail fast with a clear error when it is missing.",
    "Add a `status` field to the `Order` model in packages/api/prisma/schema.prisma and to the `Order` interface.",
    "`fetchOrders` in packages/web/src/api.ts should pass the limit through as a parameter.",
    "Add a vitest for `listOrders` in packages/api/test/orders.test.ts, mocking `db.query`.",
    "The `totalCents` field should be formatted as dollars in packages/web; add a `formatCents` helper.",
]


def _repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _payload(repo: Path, text: str, session: str) -> dict:
    return {"session_id": session, "turn_id": "t", "cwd": str(repo), "hook_event_name": "UserPromptSubmit", "prompt": text}


def _notes(files: dict[str, str], prompts: list[str], tmp_path: Path) -> dict[str, str]:
    repo = _repo(tmp_path / "repo", files)
    guard = Guard(Settings())
    spoke: dict[str, str] = {}
    try:
        guard.workspace(repo).index.ready(timeout=30)
        for n, prompt in enumerate(prompts):
            out, _rendering, _decision = translate.dispatch(guard, _payload(repo, prompt, f"s{n}"))
            if out:
                spoke[prompt] = str(out.get("hookSpecificOutput", {}).get("additionalContext", out))[:300]
    finally:
        guard.close()
    return spoke


def _first_edits_held(files: dict[str, str], prompts: list[str], tmp_path: Path, patch: str) -> list[str]:
    repo = _repo(tmp_path / "repo", files)
    guard = Guard(Settings())
    held: list[str] = []
    try:
        guard.workspace(repo).index.ready(timeout=30)
        for n, prompt in enumerate(prompts):
            translate.dispatch(guard, _payload(repo, prompt, f"h{n}"))
            edit = {
                "session_id": f"h{n}", "turn_id": "t", "cwd": str(repo), "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch", "tool_input": {"command": patch}, "tool_use_id": f"call-{n}",
            }
            out = translate.handle_payload(guard, edit)
            if out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
                held.append(prompt)
    finally:
        guard.close()
    return held


def test_web_and_data_prompts_python_get_no_premise_note(tmp_path):
    spoke = _notes(WEB_PY, PY_PROMPTS, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


@Q4
def test_web_and_data_prompts_monorepo_get_no_premise_note(tmp_path):
    spoke = _notes(WEB_TS, TS_PROMPTS, tmp_path)
    assert spoke == {}, "\n".join(f"{p!r}\n    -> {n}" for p, n in spoke.items())


@Q4
def test_first_edit_after_web_prompts_is_not_held(tmp_path):
    py_patch = "*** Begin Patch\n*** Update File: src/stockroom/app.py\n@@\n from flask import Flask, jsonify\n+import os\n*** End Patch"
    ts_patch = "*** Begin Patch\n*** Update File: packages/api/src/server.ts\n@@\n import express from \"express\";\n+import { randomUUID } from \"node:crypto\";\n*** End Patch"
    held = _first_edits_held(WEB_PY, PY_PROMPTS, tmp_path / "py", py_patch)
    held += _first_edits_held(WEB_TS, TS_PROMPTS, tmp_path / "ts", ts_patch)
    assert held == [], "\n".join(held)
