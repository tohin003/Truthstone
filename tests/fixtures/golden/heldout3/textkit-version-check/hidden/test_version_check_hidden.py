"""textkit.compat.satisfies and `textkit check-version`: PEP 440 specifiers against
textkit.__version__ (1.4.0 today; the cases are written relative to it), invalid specifiers
refused; the other commands unchanged."""

import pytest

import textkit
from textkit.cli import main
from textkit.compat import satisfies

M, m, p = (int(part) for part in textkit.__version__.split(".")[:3])

SATISFIED = [
    f">={M}.{m},<{M + 1}",
    f">={M}.{m}, <{M + 1}",
    f">={M}.{m}",
    f"=={M}.{m}.{p}",
    f"=={M}.{m}.*",
    f"~={M}.{m}",
    f"~={M}.{m}.{p}",
    f"<{M}.{m + 1}",
    f"!={M}.{m}.{p + 1}",
    f">={M}.{m}.{p}rc1",
]
NOT_SATISFIED = [
    f">={M}.{m + 1}",
    f"<{M}.{m}",
    f"!={M}.{m}.{p}",
    f">={M + 1}",
    f"=={M}.{m}.{p + 1}",
    f"<{M}.{m}.{p}",
    f"=={M}.{m + 1}.*",
    f"~={M}.{m + 1}.0",
]


def run(capsys, *argv):
    try:
        status = main(list(argv))
    except SystemExit as exc:  # an implementation may exit through argparse-style SystemExit
        status = exc.code
    out = capsys.readouterr()
    return status, out.out, out.err


@pytest.mark.parametrize("spec", SATISFIED)
def test_satisfied_specifiers(spec):
    assert satisfies(spec) is True


@pytest.mark.parametrize("spec", NOT_SATISFIED)
def test_specifiers_that_are_not_satisfied(spec):
    assert satisfies(spec) is False


@pytest.mark.parametrize("spec", ["1.4", ">=one", "=>1.4", "latest"])
def test_invalid_specifiers_raise_value_error(spec):
    with pytest.raises(ValueError):
        satisfies(spec)


def test_check_version_exits_0_when_satisfied(capsys):
    status, out, _ = run(capsys, "check-version", SATISFIED[0])
    assert status == 0
    assert textkit.__version__ in out


def test_check_version_exits_1_when_not_satisfied(capsys):
    status, out, err = run(capsys, "check-version", NOT_SATISFIED[0])
    assert status == 1
    assert textkit.__version__ in out + err


def test_check_version_exits_2_for_an_invalid_specifier(capsys):
    status, _, err = run(capsys, "check-version", "latest")
    assert status == 2
    assert err


def test_the_other_commands_are_unchanged(capsys):
    assert main(["case", "--style", "kebab", "Hello World"]) == 0
    assert capsys.readouterr().out == "hello-world\n"
    assert main(["slug", "Crème Brûlée"]) == 0
    assert capsys.readouterr().out == "creme-brulee\n"
