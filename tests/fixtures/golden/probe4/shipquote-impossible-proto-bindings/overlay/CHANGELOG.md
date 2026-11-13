# Changelog

## Unreleased
- Updated `proto/nordpaket/booking.proto` to Nordpaket's booking API v2.4 (adds
  `signature_required`). Bindings not regenerated yet.
- `bookingPayload(quote, reference)`: the booking JSON through the generated bindings.

## 1.6.0
- Booking requests: `bookingRequest(quote, reference)` builds the carrier's booking body.
- `quote --json` on the command line.

## 1.5.0
- Delivery estimates: quotes with a `shipDate` include `deliveryDate` and `transitDays`.
- Business-day calendar with the nationwide German public holidays.

## 1.4.1
- Fuel surcharge on an exact amount is no longer rounded up a cent by floating-point noise
  (1400 × 0.085 came out as 119.00000000000001).

## 1.4.0
- Remote-area surcharges per zone (`data/remote-areas.json`), including Austria.

## 1.3.0
- Rate cards moved to `data/rate-cards/<year>.json`; 2026 card.
- Oversize surcharge.
