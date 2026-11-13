# Known issues

Tests that fail on main on purpose. Each one waits for a decision; don't fix them as part of other
changes.

- **#58** `tests/test_cache.py::test_entries_expire_after_their_ttl`. Whether cached responses
  expire per entry or for the whole cache at once is not decided yet. The test pins the per-entry
  proposal so the discussion has something concrete to run, and it fails until the decision is
  made: `LRUCache` has no expiry today. Owner: Mia (platform).
