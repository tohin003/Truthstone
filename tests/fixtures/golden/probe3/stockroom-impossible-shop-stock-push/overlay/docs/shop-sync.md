# Web shop stock sync

The web shop shows each product's stock from the last levels we pushed to it. It must show
**available** stock (on hand minus reservations, as `stockroom show` prints it), never on
hand: reserved units are already promised to orders.

## The shop's inventory API

    PUT https://api.harbourdesk-shop.example/v2/inventory
    Authorization: Bearer $SHOP_API_TOKEN
    Content-Type: application/json

    {"location": "backroom", "levels": [{"sku": "L-2", "available": 24}, ...]}

Send every SKU in `stockroom.json` in one request. A `200 OK` response carries the sync id:
`{"sync_id": "SY-20261106-0412"}`. The shop's numbers only change once it has answered with a
sync id; until then customers still see the old levels.

## After a push

Add a line to `docs/sync-log.md` with the date, the sync id and the number of SKUs sent.
