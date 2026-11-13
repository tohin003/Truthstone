# On-call runbook: switching a flag off

Any flag can be forced off in the service that evaluates it with `FLAGKIT_<KEY>=off` (see the
README, "Environment overrides"), without a deploy: set the variable on the service and restart
it. Switching one flag off must never switch off another.

| service        | config                  | flag              | variable                  |
| -------------- | ----------------------- | ----------------- | ------------------------- |
| storefront     | `flags/storefront.json` | `new-checkout`    | `FLAGKIT_NEW_CHECKOUT`    |
| storefront     | `flags/storefront.json` | `search-v2`       | `FLAGKIT_SEARCH_V2`       |
| storefront     | `flags/storefront.json` | `gift-cards`      | `FLAGKIT_GIFT_CARDS`      |
| storefront     | `flags/storefront.json` | `dark-mode`       | `FLAGKIT_DARK_MODE`       |
| mobile backend | `flags/mobile.json`     | `one-tap-reorder` | `FLAGKIT_ONE_TAP_REORDER` |
| mobile backend | `flags/mobile.json`     | `offline-cart`    | `FLAGKIT_OFFLINE_CART`    |
| mobile backend | `flags/mobile.json`     | `search.v2`       | `FLAGKIT_SEARCH_V2`       |

Each service loads only its own config, so a variable reaches only the flags in that file.
