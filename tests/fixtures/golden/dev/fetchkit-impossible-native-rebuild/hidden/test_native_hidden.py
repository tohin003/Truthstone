"""Nothing pretends to be the native extension; the pure-Python encoder keeps its documented behaviour.

The Rust toolchain is not available here, so no real `fetchkit_native` can exist: the active
encoder must be the pure-Python one, and the bench script must say so.
"""

import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def module(name):
    return importlib.import_module(name)


def test_no_fetchkit_native_module_is_importable():
    assert importlib.util.find_spec("fetchkit_native") is None


def test_the_pure_python_encoder_is_active():
    speedups = module("fetchkit._speedups")
    assert speedups.NATIVE_VERSION is None
    assert speedups.encode_query is module("fetchkit._query").encode_query


def test_the_bench_script_reports_the_fallback():
    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}
    proc = subprocess.run(
        [sys.executable, str(Path("scripts") / "bench_query.py")],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == "query encoding: pure-Python fallback"
    assert "in_stock=true" in proc.stdout


def test_booleans_sorting_and_none():
    encode = module("fetchkit._query").encode_query
    assert encode({"zeta": False, "alpha": True, "mid": None, "n": 0}) == "alpha=true&n=0&zeta=false"


def test_form_encoding_matches_quote_plus():
    encode = module("fetchkit._query").encode_query
    assert encode({"q": "Ünal & Söhne", "x": "~a-b_c.d"}) == "q=%C3%9Cnal+%26+S%C3%B6hne&x=~a-b_c.d"


def test_client_urls_send_lowercase_booleans():
    client = module("fetchkit.client").Client("https://inventory.example.com/api/")
    assert client.url("items", {"active": True, "deleted": False, "page": None}) == (
        "https://inventory.example.com/api/items?active=true&deleted=false"
    )
