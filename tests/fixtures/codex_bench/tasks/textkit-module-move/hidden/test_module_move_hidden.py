"""legacy_case is folded into case: same names, same behaviour, and every former user still works."""

import importlib.util
from pathlib import Path

import textkit
from textkit import case
from textkit.cli import converter, main
from textkit.keys import rename_keys


def test_legacy_module_is_gone():
    assert not Path("src/textkit/legacy_case.py").exists()
    assert importlib.util.find_spec("textkit.legacy_case") is None


def test_old_helpers_live_in_case_with_their_old_behaviour():
    assert case.underscore("createdAt") == "created_at"
    assert case.underscore("parseHTTPResponse") == "parse_httpresponse"
    assert case.dasherize("Hello_World again") == "Hello-World-again"
    assert case.camelize("hello_world") == "HelloWorld"
    assert case.camelize("hello_world", upper_first=False) == "helloWorld"
    assert case.humanize("created_at") == "Created at"


def test_modern_helpers_are_unchanged():
    assert case.to_snake("parseHTTPResponse") == "parse_http_response"
    assert case.to_camel("parse http response") == "parseHttpResponse"
    assert case.to_kebab("Parse_HTTP_Response") == "parse-http-response"
    assert case.title_case("a tale of two cities") == "A Tale of Two Cities"


def test_rename_keys_still_works():
    assert rename_keys({"createdAt": {"displayName": 1}}) == {"created_at": {"display_name": 1}}
    assert rename_keys({"created_at": 1}, "camel") == {"createdAt": 1}
    assert rename_keys({"created_at": 1}, "pascal") == {"CreatedAt": 1}


def test_package_level_names_still_work():
    assert textkit.camelize("hello_world") == "HelloWorld"
    assert textkit.humanize("updated_by") == "Updated by"


def test_cli_human_style(capsys):
    assert converter("human")("first_name") == "First name"
    assert main(["case", "--style", "human", "created_at"]) == 0
    assert capsys.readouterr().out == "Created at\n"


def test_cli_labels_command(capsys):
    assert main(["labels", "created_at", "updated_by"]) == 0
    assert capsys.readouterr().out == "Created at\nUpdated by\n"
