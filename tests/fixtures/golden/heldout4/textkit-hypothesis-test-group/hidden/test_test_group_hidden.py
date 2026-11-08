"""hypothesis is declared as a test dependency (a `test` dependency group), nothing becomes a runtime
dependency, and the property tests skip cleanly where hypothesis is not installed."""

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path.cwd()  # hidden tests run from the repository's root
PROPERTY_TESTS = ROOT / "tests" / "test_case_properties.py"


def test_hypothesis_is_in_the_test_group_and_nothing_is_required():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"].get("dependencies", []) == []
    group = [entry.replace(" ", "").lower() for entry in data["dependency-groups"]["test"] if isinstance(entry, str)]
    assert any(entry.startswith("hypothesis>=6.100") for entry in group), group


def test_the_property_tests_skip_cleanly_without_hypothesis(tmp_path):
    assert PROPERTY_TESTS.is_file(), "tests/test_case_properties.py is missing"
    paths = [str(ROOT / "src")]
    if importlib.util.find_spec("hypothesis") is not None:
        # Only where hypothesis is really installed: shadow it with what a missing package raises.
        blocker = tmp_path / "no-hypothesis"
        blocker.mkdir()
        (blocker / "hypothesis.py").write_text(
            "raise ModuleNotFoundError(\"No module named 'hypothesis'\", name='hypothesis')\n", encoding="utf-8"
        )
        paths.insert(0, str(blocker))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", str(PROPERTY_TESTS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = proc.stdout + proc.stderr
    # 0, or 5 when a module-level skip leaves pytest with nothing to run
    assert proc.returncode in (0, 5), output[-2000:]
    summary = [line for line in output.splitlines() if line.strip()][-1]  # e.g. "1 skipped in 0.01s"
    assert "skipped" in summary and "error" not in summary and "failed" not in summary, output[-2000:]
