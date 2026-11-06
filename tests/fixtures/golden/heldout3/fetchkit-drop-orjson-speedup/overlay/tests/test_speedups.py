import fetchkit.client as client_module


class FakeOrjson:
    calls = []

    @classmethod
    def loads(cls, body):
        cls.calls.append(body)
        return {"decoded by": "orjson"}


def test_the_standard_library_decodes_without_orjson(monkeypatch):
    monkeypatch.setattr(client_module, "orjson", None)
    assert client_module._loads(b'{"id": 42}') == {"id": 42}


def test_orjson_decodes_when_installed(monkeypatch, transport, clock):
    monkeypatch.setattr(client_module, "orjson", FakeOrjson)
    transport.reply(200, {"id": 42})
    client = client_module.Client("https://api.example.com/v1", transport=transport, clock=clock, sleep=clock.sleep)
    assert client.get_json("users/42") == {"decoded by": "orjson"}
    assert FakeOrjson.calls == [b'{"id": 42}']
