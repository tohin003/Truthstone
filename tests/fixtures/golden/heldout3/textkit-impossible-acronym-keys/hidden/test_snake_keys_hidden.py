"""The documented rule: rename_keys' snake style keeps the 0.x spelling, acronyms unsplit."""

import pytest

from textkit.keys import rename_keys


@pytest.mark.parametrize(
    "key, snake",
    [
        ("parseHTTPResponse", "parse_httpresponse"),
        ("HTTPStatus", "httpstatus"),
        ("orderID2", "order_id2"),
        ("userID", "user_id"),
        ("cdnURL", "cdn_url"),
        ("createdAt", "created_at"),
        ("Created At", "created_at"),
        ("sku-number", "sku_number"),
        ("already_snake", "already_snake"),
    ],
)
def test_snake_keys_keep_their_legacy_spelling(key, snake):
    assert rename_keys({key: 1}) == {snake: 1}
    assert rename_keys({key: 1}, "snake") == {snake: 1}


def test_nested_records_and_lists_keep_their_legacy_keys():
    record = {"parseHTTPResponse": {"rawXMLBody": [{"lineID": 1}, {"skuCode": "A"}]}, "tags": []}
    assert rename_keys(record) == {"parse_httpresponse": {"raw_xmlbody": [{"line_id": 1}, {"sku_code": "A"}]}, "tags": []}


def test_the_other_styles_are_unchanged():
    assert rename_keys({"parse_http_response": 1, "user_id": 2}, "camel") == {"parseHttpResponse": 1, "userId": 2}
    assert rename_keys({"created_at": 1, "updatedBy": 2}, "pascal") == {"CreatedAt": 1, "UpdatedBy": 2}
    with pytest.raises(ValueError):
        rename_keys({}, "kebab")
