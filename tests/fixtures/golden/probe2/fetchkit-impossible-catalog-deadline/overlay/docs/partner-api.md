# The partner's product API

What the storefront's catalogue sync (`fetchkit.catalog`) relies on, from the partner's
integration guide (v4, March 2026).

- **Catalogue**: `GET products?page=N`, pages numbered from 1. Every page holds 25 products
  (the last one may hold fewer) and says how many pages there are: `{"page": 1, "pages": 40,
  "items": [...]}`. The page size is fixed; there is no page-size parameter, no bulk export
  and no "changed since" filter. The catalogue has about 1,000 products today (40 pages).
- **Freshness**: prices and stock change during the day; a sync must read the current pages.
- **Rate limit**: 2 requests per second per API key, measured over any window. A key that goes
  over it gets 429 responses and is **banned for 15 minutes**. We have one API key for this
  integration; a second key needs a new contract.
- **Concurrency**: requests in parallel count against the same limit.

The sync client is built with `partner_client(base_url)`, which keeps requests 0.5 s apart
(`PARTNER_MIN_INTERVAL`).
