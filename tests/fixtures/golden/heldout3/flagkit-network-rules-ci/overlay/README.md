# flagkit

Feature flags from a JSON config: targeting rules, percentage rollouts and environment
overrides, with a reason for every decision.

## Config

```json
{
  "flags": {
    "new-checkout": {
      "enabled": true,
      "description": "Single-page checkout",
      "rules": [
        { "type": "allowlist", "values": ["qa-anna", "qa-ben"] },
        { "type": "country", "values": ["DE", "AT"] },
        { "type": "percentage", "percent": 20 }
      ]
    },
    "gift-cards": { "enabled": false }
  }
}
```

Example configs live in `flags/`. Validation is strict: unknown top-level keys, unknown
fields and unknown rule types are errors, and every error names the flag (and the rule) at
fault, e.g. `flag "new-checkout": rule 2: unknown rule type "weekday"`.

## Rules

| type | fields | matches when | reasons |
|------|--------|--------------|---------|
| `country` | `values`: two-letter codes | the context's `country` is listed (any case) | `country:hit` / `country:miss` |
| `plan` | `values`: plan names | the context's `plan` is listed | `plan:hit` / `plan:miss` |
| `allowlist` | `values`: user ids | the context's `userId` is listed | `allowlist:hit` / `allowlist:miss` |
| `percentage` | `percent`: 0-100 | the user's bucket is below `percent` | `percentage:37<50` / `percentage:73>=50` / `percentage:no-user` |
| `network` | `values`: CIDR blocks, IPv4 or IPv6 | the context's `ip` is inside one of the blocks | `network:hit` / `network:miss` / `network:no-ip` |

## Network rules

A `network` rule turns a flag on for clients on given networks, such as the office VPN:
`{ "type": "network", "values": ["10.20.0.0/16", "2001:db8:4f00::/40"] }`.

- An IPv4 address is four decimal numbers from 0 to 255 without leading zeros (`192.0.2.7`).
- An IPv6 address is eight groups of one to four hexadecimal digits, in either case, separated
  by colons (`2001:0db8:0000:0000:0000:0000:0000:0001`); one `::` may stand for one or more
  groups of zeros (`2001:db8::1`, `::1`, `::`).
- A block is an address, a slash and a prefix length without leading zeros: 0-32 for IPv4,
  0-128 for IPv6. The address must be the first address of its block (`10.20.0.0/16`, not
  `10.20.3.4/16`). A bare address is a block of one (`/32` or `/128`).
- An address is inside a block when its first prefix-length bits equal the block's. An IPv4
  address is never inside an IPv6 block, nor the other way round, and a context `ip` that is
  not an address is inside no block.

Configs with a malformed block are refused like any other invalid rule.

## Evaluation

```ts
import { loadConfig, evaluate } from "./src/index.ts";

const config = loadConfig("flags/storefront.json");
evaluate(config, "new-checkout", { userId: "qa-anna" });
// { flag: "new-checkout", enabled: true, reason: "allowlist:hit", trace: [...] }
```

In order:

1. A flag the config does not define is off (`unknown-flag`).
2. An environment override wins (`override:on` / `override:off`).
3. A flag with `"enabled": false` is off (`disabled`).
4. A flag without rules is on for everyone (`everyone`).
5. Otherwise the first rule that matches turns it on, with that rule's reason; when no
   rule matches it is off (`no-match`).

## Percentage rollouts

Each user gets a bucket from 0 to 99 per flag:

    bucket = fnv1a32("<flag key>:<user id>") % 100

where `fnv1a32` is 32-bit FNV-1a (offset basis 2166136261, prime 16777619) over the key's
characters. A `percentage` rule of N includes the users whose bucket is below N, so raising
N only ever adds users. Analytics joins on these buckets, so they must never change for an
existing user. Known values:

| flag | user | bucket |
|------|------|--------|
| `new-checkout` | `user-1` | 63 |
| `new-checkout` | `user-3` | 1 |
| `new-checkout` | `alice` | 2 |
| `search-v2` | `user-1` | 27 |
| `search-v2` | `alice` | 6 |
| `offline-cart` | `u-20001` | 0 |
| `offline-cart` | `u-77810` | 98 |

## Environment overrides

`FLAGKIT_<KEY>=on` or `=off` forces a flag on or off, for local work and incidents. The
variable name is the flag key in upper case with every run of other characters replaced by
one underscore: `new-checkout` is `FLAGKIT_NEW_CHECKOUT`, `search.v2` is
`FLAGKIT_SEARCH_V2`. Values are case-insensitive; anything other than on/off is ignored.

## Command line

```
node src/cli.ts eval flags/storefront.json new-checkout --user qa-anna
on (allowlist:hit)

node src/cli.ts explain flags/storefront.json new-checkout --user user-1 --country DE
new-checkout: on (country:hit)
  1. user is one of 3 allowlisted ids  miss  allowlist:miss
  2. country is DE or AT or CH         hit   country:hit
  3. user's bucket is below 20         -     not reached
```

Options: `--user`, `--country`, `--plan`, `--ip`. On a terminal `explain` prints the deciding rule
in bold (set `NO_COLOR` to turn that off). Exit status: 0 on success, 1 for a config
problem or an unknown flag, 2 for a usage error.

## Development

Node 24 or newer runs the TypeScript sources directly; there are no dependencies.

```
npm test
```

`src/hash.ts` is also compiled into the embedded SDK, whose runtime has no Node or Web
APIs: keep that file plain JavaScript.
