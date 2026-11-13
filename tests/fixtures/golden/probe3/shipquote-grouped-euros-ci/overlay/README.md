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

## Amounts in euros

`parseEuros(text)` reads an amount in euros typed by a person or exported by a spreadsheet,
and returns cents:

- one decimal separator, `.` or `,`, followed by one or two digits: `7.49`, `7,49`, `7.5`, or
  none at all: `7`;
- thousands separators in either convention, when the amount also has decimals after the
  other separator (`1.240,50`, `1,240.50`) or when the same separator appears more than once
  (`1.240.000`, `2,500,000`). The first group has one to three digits and every later group
  exactly three, and the decimal separator, if any, comes once, last;
- a single separator followed by three digits (`1.240`, `7.499`) is ambiguous and rejected, as
  is anything else that does not follow these rules (signs, currency symbols, exponents).

Surrounding spaces are ignored. `test/money-grouping.test.ts` is the specification for the
grouped forms.

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
