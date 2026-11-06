import pytest

from textkit.keys import rename_keys


def test_rename_keys_to_snake_case_recursively():
    record = {"createdAt": 1, "owner": {"displayName": "Ada"}, "tags": [{"tagId": 7}]}
    assert rename_keys(record) == {
        "created_at": 1,
        "owner": {"display_name": "Ada"},
        "tags": [{"tag_id": 7}],
    }


def test_rename_keys_to_camel_and_pascal():
    assert rename_keys({"created_at": 1, "updatedBy": 2}, "camel") == {"createdAt": 1, "updatedBy": 2}
    assert rename_keys({"created_at": 1}, "pascal") == {"CreatedAt": 1}
    with pytest.raises(ValueError):
        rename_keys({}, "shouty")


def test_snake_case_splits_acronyms_for_the_public_api():
    # API-112: the public API's style guide wants every acronym as a word of its own.
    record = {"userID": 7, "parseHTTPResponse": True, "owner": {"cdnURL": "https://api.example.com"}}
    assert rename_keys(record) == {
        "user_id": 7,
        "parse_http_response": True,
        "owner": {"cdn_url": "https://api.example.com"},
    }
