# fetchkit

A tiny client for JSON-over-HTTP APIs, used by our internal services. It has no runtime
dependencies: the default transport is `urllib` from the standard library.

## Usage

```python
from fetchkit import Client

client = Client("https://api.example.com/v1", headers={"Authorization": "Bearer ..."})
user = client.get_json("users/42")
hits = client.get_json("search", params={"q": "desk lamp", "page": 2})
```

Paths are joined onto the base URL. Query parameters are sorted and `None` values are
dropped, so equal requests produce equal URLs. See "URLs" below for the exact rules.

## URLs

`client.url()`, which every request goes through, builds URLs that are safe to send as
they are:

- Paths are taken literally and each segment is percent-encoded: `annual report.pdf` ->
  `annual%20report.pdf`, `Zoë` -> `Zo%C3%AB`, a literal `%` -> `%25`. When a segment may
  itself contain `/`, pass the path as a sequence of segments, e.g.
  `("customers", "Ünal / Söhne")`; `get_json` accepts the same.
- An internationalised host name in the base URL is sent in its ASCII (IDNA) form:
  `https://bücher.example:8443` -> `https://xn--bcher-kva.example:8443`.
- Query values are form-encoded as UTF-8 (a space becomes `+`, reserved characters such as
  `&`, `=`, `+`, `/` and `%` are percent-encoded), parameters are sorted by name, `None` is
  dropped, and a list value repeats the parameter in order: `{"tag": ["b", "a"]}` ->
  `tag=b&tag=a`.

## Errors

Everything fetchkit raises derives from `fetchkit.FetchError`:

- `TransportError`: no response arrived (connection refused, DNS failure, timeout).
- `ClientError`: a 4xx response. `.status`, `.url` and `.body` describe it.
- `ServerError`: a 5xx response, with the same attributes.
- `DecodeError`: the body was not valid JSON.

## Caching

`Client(..., cache=LRUCache(maxsize=256))` reuses decoded responses for repeated GETs of
the same URL. Error responses are never cached.

## Rate limits

`Client(..., min_interval=0.5)` keeps successive requests at least half a second apart.

## Development

The deploy pipeline runs `pytest` on main and deploys only a green build.

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.
