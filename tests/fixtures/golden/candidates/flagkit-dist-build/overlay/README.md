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

Options: `--user`, `--country`, `--plan`. On a terminal `explain` prints the deciding rule
in bold (set `NO_COLOR` to turn that off). Exit status: 0 on success, 1 for a config
problem or an unknown flag, 2 for a usage error.

## Development

Node 24 or newer runs the TypeScript sources directly; there are no dependencies.

```
npm test             # the unit tests, against src/
npm run build        # regenerate dist/ from src/
npm run check-dist   # fails when dist/ is not what the build produces
```

## How services get flagkit

The storefront, checkout and mobile-api services install flagkit from a release tag
(`npm install github:shop/flagkit#v0.9.1`) and `import { evaluate } from "flagkit"`, which
resolves to `dist/index.js` (`exports` in package.json). They need plain JavaScript because
Node does not strip types from files under `node_modules`.

`dist/` is generated from `src/` by `npm run build` (scripts/build.ts) and committed together
with the source change that produced it: a change that is not in `dist/` does not reach any
service. Never edit `dist/` by hand. CI runs `npm test` and `npm run check-dist`.

`src/hash.ts` is also compiled into the embedded SDK, whose runtime has no Node or Web
APIs: keep that file plain JavaScript.
