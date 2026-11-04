from textkit.case import split_words, title_case, to_camel, to_kebab, to_snake


def test_split_words_handles_humps_and_acronyms():
    assert split_words("parseHTTPResponse") == ["parse", "HTTP", "Response"]
    assert split_words("user_id-list item") == ["user", "id", "list", "item"]


def test_snake_and_kebab():
    assert to_snake("parseHTTPResponse") == "parse_http_response"
    assert to_snake("Hello World") == "hello_world"
    assert to_kebab("Parse_HTTP_Response") == "parse-http-response"


def test_camel():
    assert to_camel("parse http response") == "parseHttpResponse"
    assert to_camel("") == ""


def test_title_case_small_words_stay_lowercase():
    assert title_case("a tale of two cities") == "A Tale of Two Cities"
    assert title_case("war and peace") == "War and Peace"


def test_title_case_first_and_last_words_are_capitalised():
    assert title_case("of mice and men") == "Of Mice and Men"
    assert title_case("what dreams are made of") == "What Dreams Are Made Of"


def test_title_case_normalises_case_and_spacing():
    assert title_case("THE  GREAT GATSBY") == "The Great Gatsby"


def test_title_case_capitalises_every_word_of_a_series_name():
    # Series names on the docs site are written with every word capitalised.
    assert title_case("the lord of the rings") == "The Lord Of The Rings"
