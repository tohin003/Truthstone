from textkit.legacy_case import camelize, dasherize, humanize, underscore


def test_underscore():
    assert underscore("createdAt") == "created_at"
    assert underscore("Hello World-Again") == "hello_world_again"
    assert underscore("parseHTTPResponse") == "parse_httpresponse"


def test_dasherize_keeps_case():
    assert dasherize("Hello_World again") == "Hello-World-again"


def test_camelize_and_humanize():
    assert camelize("hello_world") == "HelloWorld"
    assert camelize("hello_world", upper_first=False) == "helloWorld"
    assert humanize("created_at") == "Created at"
