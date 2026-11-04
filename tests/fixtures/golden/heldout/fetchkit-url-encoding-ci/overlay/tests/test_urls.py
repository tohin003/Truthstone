from fetchkit.client import Client

BASE = "https://api.example.com/v1"


def test_path_segments_are_percent_encoded():
    client = Client(BASE)
    assert client.url("files/annual report 2026.pdf") == f"{BASE}/files/annual%20report%202026.pdf"
    assert client.url("people/Zoë") == f"{BASE}/people/Zo%C3%AB"
    assert client.url(("customers", "Ünal / Söhne", "orders")) == (
        f"{BASE}/customers/%C3%9Cnal%20%2F%20S%C3%B6hne/orders"
    )
    assert client.url("users/42") == f"{BASE}/users/42"


def test_international_host_names_are_sent_as_idna():
    client = Client("https://bücher.example:8443/api")
    assert client.url("books") == "https://xn--bcher-kva.example:8443/api/books"


def test_query_values_are_encoded_and_lists_repeat_the_key():
    url = Client(BASE).url("search", {"q": "Ünal & Söhne", "tag": ["new", "50%"], "page": 2, "sort": None})
    assert url == f"{BASE}/search?page=2&q=%C3%9Cnal+%26+S%C3%B6hne&tag=new&tag=50%25"
