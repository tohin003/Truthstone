# shipquote

Parcel shipping quotes for the shop's checkout: Nordpaket base rates, surcharges and
delivery estimates, as integer euro cents.

## Usage

```ts
import { quote, formatEUR } from "./src/index.ts";

const q = quote({
  country: "DE",
  postcode: "10115",
  parcel: { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 },
  shipDate: "2026-11-05", // optional: adds deliveryDate and transitDays
});
q.zone;                   // 1
q.billableKg;             // 2.5
q.lines;                  // [{ code: "base", label: "Base rate, zone 1 (...), up to 5 kg", amountCents: 690 },
                          //  { code: "fuel", label: "Fuel surcharge 8.5%", amountCents: 59 }]
formatEUR(q.totalCents);  // "€7.49"
q.deliveryDate;           // "2026-11-06"
```

`bookingRequest(quote, reference)` turns a quote into the body of the carrier's booking
request (amounts as `"6.90"` strings).

## Rules

### Zones

| zone | covers |
|------|--------|
| 1 | Germany North & East: DE postcodes 0xxxx-2xxxx |
| 2 | Germany West & Centre: DE postcodes 3xxxx-6xxxx |
| 3 | Germany South: DE postcodes 7xxxx-9xxxx |
| 4 | Austria: every AT postcode |

German postcodes have five digits (leading zeros count: 01067 is Dresden), Austrian ones
four. Spaces are ignored. We do not ship anywhere else.

### Billable weight

The carrier bills the greater of the actual weight and the volumetric weight
(length × width × height in cm / 5000), **rounded up to the next 0.5 kg**. Parcels over
31.5 kg billable are refused.

### Base rate

`data/rate-cards/<year>.json` holds the carrier's rate card for a year: weight brackets
(up to 1, 2, 5, 10, 20 and 31.5 kg) and the price of each bracket per zone. Quotes use
the 2026 card (`DEFAULT_YEAR` in `src/rates.ts`) unless they pass a `year`.

### Surcharges

- **Fuel**: 8.5 % of the base rate, rounded up to the next cent.
- **Remote areas**: islands and a few mountain areas listed per zone in
  `data/remote-areas.json`, each zone with its own flat surcharge.
- **Oversize**: €12.00 when the longest side is over 120 cm or length plus girth
  (longest side + 2 × each other side) is over 300 cm.

### Delivery estimates

Transit takes 1 business day to zones 1 and 2, 2 to zone 3 and 3 to Austria, counted from
the day after pickup. Business days are Monday to Friday except the nationwide German
public holidays (New Year's Day, Good Friday, Easter Monday, Labour Day, Ascension Day,
Whit Monday, German Unity Day, Christmas Day and Boxing Day).

## Tracking numbers

Every parcel label carries a tracking number in the UPU S10 format that Nordpaket's scanners
read: two service letters (`CP` for our parcels), an eight-digit serial, one check digit and the
origin country (`DE`), e.g. `CP000012349DE`. `src/tracking.ts` makes and checks them.

- `trackingNumber(serial)`: the serial is a whole number from 0 to 99,999,999 (anything else is a
  `RangeError`), written with eight digits, leading zeros included.
- The check digit: multiply the eight serial digits by 8, 6, 4, 2, 3, 5, 9 and 7, add up the
  products and take the remainder of the sum divided by 11. The check digit is 11 minus that
  remainder, except that 10 is written as 0 and 11 as 5.
- `isValidTrackingNumber(text)`: true for two letters, eight digits, the right check digit and two
  letters, in either case and with spaces anywhere (labels print `CP 0000 1234 9 DE`). Any service
  letters and country are accepted, so other carriers' numbers validate too: the standard's own
  example is `RR473124829GB`.
- `formatTrackingNumber(text)`: the label form, in upper case and in groups of 2, 4, 4, 1 and 2
  characters: `CP 0000 1234 9 DE`.

## Command line

```
node src/cli.ts quote --postcode 10115 --weight 2.3 --dims 20x15x10 [--country DE] [--ship-date 2026-11-05] [--year 2026] [--json]
node src/cli.ts zones
```

```
$ node src/cli.ts quote --postcode 10115 --weight 2.3 --dims 20x15x10
To DE 10115 (zone 1), billable weight 2.5 kg
  Base rate, zone 1 (Germany North & East), up to 5 kg      €6.90
  Fuel surcharge 8.5%                                       €0.59
  Total                                                     €7.49
```

Exit status: 0 on success, 1 when the destination or parcel cannot be quoted, 2 on a usage
error.

## Development

Node 24 or newer runs the TypeScript sources directly (type stripping); there are no
dependencies to install.

```
npm test
```
