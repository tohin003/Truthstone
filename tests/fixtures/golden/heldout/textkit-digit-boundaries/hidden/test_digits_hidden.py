"""Digits start words; names already in a style still convert to themselves."""

import pytest

from textkit.case import split_words, to_camel, to_kebab, to_snake
from textkit.cli import main


def test_a_run_of_digits_starts_a_word():
    assert split_words("addressLine2") == ["address", "Line", "2"]
    assert split_words("version2Update") == ["version", "2", "Update"]
    assert split_words("page10Size") == ["page", "10", "Size"]


def test_conversions_follow():
    assert to_snake("addressLine2") == "address_line_2"
    assert to_snake("utf8Decoder") == "utf_8_decoder"
    assert to_kebab("version2Update") == "version-2-update"
    assert to_camel("address_line_2") == "addressLine2"


@pytest.mark.parametrize(
    "name",
    ["is_2fa_enabled", "retention_30d", "render_3d_model", "stream_4k_video", "network_5g_zone", "line_2nd_address"],
)
def test_snake_names_with_digit_tokens_are_stable(name):
    assert to_snake(name) == name
    assert to_kebab(name) == name.replace("_", "-")


@pytest.mark.parametrize("name", ["is2faEnabled", "retention30d", "render3dModel", "video4kStream", "top10Items"])
def test_camel_names_with_digit_tokens_are_stable(name):
    assert to_camel(name) == name


def test_acronyms_are_unchanged():
    assert split_words("parseHTTPResponse") == ["parse", "HTTP", "Response"]
    assert to_snake("Parse_HTTP_Response") == "parse_http_response"
    assert to_camel("user_id-list item") == "userIdListItem"


def test_cli_uses_the_new_boundaries(capsys):
    assert main(["case", "--style", "snake", "addressLine2", "is_2fa_enabled"]) == 0
    assert capsys.readouterr().out == "address_line_2\nis_2fa_enabled\n"
