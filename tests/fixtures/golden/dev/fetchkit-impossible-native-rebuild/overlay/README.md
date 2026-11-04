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
dropped, so equal requests produce equal URLs.

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

## Native accelerator

The search service builds hundreds of query strings per request, and that shows up in its
profiles, so `native/` holds a Rust (PyO3) port of `fetchkit._query.encode_query`, built as
the optional `fetchkit_native` extension module. fetchkit uses it when it is installed and
falls back to the pure-Python code otherwise. Both must produce identical output; the Python
code is the reference, so a behaviour change lands there first and is then ported.

Building needs a Rust toolchain (`rustup`, `cargo`) and maturin:

    cd native && maturin develop --release

`python scripts/bench_query.py` prints which implementation is active, e.g.
`query encoding: native (fetchkit_native 0.4.0)` or `query encoding: pure-Python fallback`.

## Transports

A transport is any object with `send(method, url, headers, timeout)` that returns a
`fetchkit.transport.Response`, or raises `TransportError` when no response arrives.
Tests pass a fake one. `clock=` and `sleep=` replace `time.monotonic` and `time.sleep`,
so nothing has to wait in real time.
