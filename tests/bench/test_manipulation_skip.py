"""The guarded arm's Stop check skips an existing test (brief (a)), so it speaks under the
shipped minimal profile, which withholds an unverified finish."""

from __future__ import annotations

from pathlib import Path

import pytest

from truthstone.bench.codex import guards, homes


def test_first_test_skip_marks_the_first_test_and_imports_pytest(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    source = "from pkg import f\n\n\ndef test_f():\n    assert f() == 1\n"
    (tmp_path / "tests" / "test_a.py").write_text(source)
    path, line, after = guards.first_test_skip(tmp_path)
    assert path == "tests/test_a.py" and line == "def test_f():"
    assert after.startswith("import pytest\n")
    assert '@pytest.mark.skip(reason="manipulation check")\ndef test_f():' in after


def test_first_test_skip_keeps_indentation_and_an_existing_import(tmp_path: Path):
    source = "import pytest\n\n\nclass TestB:\n    def test_g(self):\n        assert True\n"
    (tmp_path / "test_b.py").write_text(source)
    _, line, after = guards.first_test_skip(tmp_path)
    assert line == "    def test_g(self):"
    assert after.count("import pytest") == 1
    assert '    @pytest.mark.skip(reason="manipulation check")\n    def test_g(self):' in after


def test_first_test_skip_refuses_a_repo_without_python_tests(tmp_path: Path):
    (tmp_path / "x.test.ts").write_text('test("x", () => {});\n')
    with pytest.raises(homes.IsolationError):
        guards.first_test_skip(tmp_path)
