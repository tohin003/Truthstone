import pytest

from textkit.cli import converter, main


def test_case_command(capsys):
    assert main(["case", "--style", "kebab", "Hello World", "parseHTTPResponse"]) == 0
    assert capsys.readouterr().out == "hello-world\nparse-http-response\n"


def test_human_style(capsys):
    main(["case", "--style", "human", "created_at"])
    assert capsys.readouterr().out == "Created at\n"


def test_slug_command_and_unknown_style(capsys):
    main(["slug", "Crème Brûlée"])
    assert capsys.readouterr().out == "creme-brulee\n"
    with pytest.raises(ValueError):
        converter("shouty")


def test_defaults_come_from_textkit_ini(tmp_path, monkeypatch, capsys):
    (tmp_path / "textkit.ini").write_text("[textkit]\nstyle = camel\nseparator = _\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["case", "Hello World"])
    main(["slug", "Crème Brûlée"])
    assert capsys.readouterr().out == "helloWorld\ncreme_brulee\n"


def test_built_in_defaults_without_textkit_ini(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["case", "Hello World"])
    main(["slug", "--separator", "_", "Crème Brûlée"])
    assert capsys.readouterr().out == "hello_world\ncreme_brulee\n"
