# Changelog

## 0.9.1
- `envName()` no longer builds a regular expression on every call.
- Test for `explain`'s terminal highlighting (see KNOWN_ISSUES.md).

## 0.9.0
- `explain` prints the deciding rule in bold on a terminal; `NO_COLOR` turns it off.
- Config errors name the rule as well as the flag.

## 0.8.0
- Strict validation: unknown top-level keys and unknown flag or rule fields are errors.

## 0.7.0
- Environment overrides: `FLAGKIT_<KEY>=on|off`.

## 0.6.0
- Removed the maintenance-banner scheduler (`src/schedule.ts` and its
  `isActiveWindow()`); banners are scheduled on the status page now.

## 0.5.0
- Percentage rollouts, bucketed with FNV-1a (see the README for the formula).
- `allowlist` rules.
