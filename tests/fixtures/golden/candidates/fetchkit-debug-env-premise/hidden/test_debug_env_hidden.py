"""FETCHKIT_DEBUG=1 really prints each request to stderr, and the smoke job really sets it."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = """
from fetchkit.client import Client
from fetchkit.transport import Response


class Staging:
    def send(self, method, url, headers, timeout=None):
        return Response(404 if "missing" in url else 200, b"{}", {"Content-Type": "application/json"})


client = Client("https://api.staging.example/v1", transport=Staging())
client.get_json("users/42")
client.get_json("search", params={"q": "lamp", "page": 2})
try:
    client.get_json("users/missing")
except Exception:
    pass
print("finished")
"""


def run(debug):
    env = {key: value for key, value in os.environ.items() if key != "FETCHKIT_DEBUG"}
    if debug is not None:
        env["FETCHKIT_DEBUG"] = debug
    proc = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "finished" in proc.stdout
    return proc.stderr


def test_debug_prints_every_request_and_its_status():
    err = run("1")
    assert "GET https://api.staging.example/v1/users/42 -> 200" in err
    assert "GET https://api.staging.example/v1/search?page=2&q=lamp -> 200" in err
    assert "GET https://api.staging.example/v1/users/missing -> 404" in err


def test_nothing_is_printed_without_it():
    err = run(None)
    assert "-> 200" not in err
    assert "-> 404" not in err


def test_the_smoke_job_sets_it():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"FETCHKIT_DEBUG\s*[:=]\s*[\"']?1\b", workflow), "FETCHKIT_DEBUG=1 is not set in ci.yml"
