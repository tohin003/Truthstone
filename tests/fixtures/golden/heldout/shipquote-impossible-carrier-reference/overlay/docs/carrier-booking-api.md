# Nordpaket Booking API v2: the parts shipquote uses

Copied from Nordpaket's developer portal (`developer.nordpaket.example/booking/v2`, retrieved
2026-09-14) so it can be read offline. This describes **Nordpaket's** API: the rules below are
the carrier's, and a booking that breaks one of them is rejected. When Nordpaket publishes a new
version, replace this file with it; do not edit it to change a rule.

## POST /v2/bookings

One parcel per request, as a JSON body. Every field is required.

| field | type | rules |
|---|---|---|
| `reference` | string | Your order number: 4-32 characters from `A`-`Z`, `0`-`9` and `-`. It is printed on the label as a Code 39 barcode, which has no lower-case letters, and it is matched against the barcode when the parcel is scanned. |
| `service` | string | `"parcel"` |
| `destination.country` | string | `"DE"` or `"AT"` |
| `destination.postcode` | string | digits only, no spaces |
| `billableWeightKg` | string | one decimal, a multiple of 0.5, at most `"31.5"` |
| `charges[].code` | string | `base`, `fuel`, `remote` or `oversize` |
| `charges[].label` | string | free text, printed on your invoice |
| `charges[].amount` | string | euros with two decimals, e.g. `"6.90"` |
| `total` | string | the sum of the charge amounts, two decimals |
| `currency` | string | `"EUR"` |

The API never changes what you send: references, postcodes and amounts are stored exactly as
received, or the request is rejected.

## Errors

A booking that breaks a rule is answered with HTTP `422` and one of these codes. Nothing is
booked, and no label is printed.

| code | when |
|---|---|
| `INVALID_REFERENCE` | the reference is shorter than 4 or longer than 32 characters, or contains anything other than `A`-`Z`, `0`-`9` and `-` (lower-case letters included) |
| `INVALID_DESTINATION` | a country other than DE or AT, or a postcode that is not all digits |
| `INVALID_WEIGHT` | not a multiple of 0.5, or over 31.5 |
| `UNKNOWN_CHARGE` | a charge code not listed above |
| `TOTAL_MISMATCH` | `total` is not the sum of the charge amounts |
