# Contributing

- `pytest` runs the unit tests in `tests/` (`testpaths` in pyproject.toml).
- `scripts/consumer-tests.sh` runs `consumers/`: the code of the services that use fetchkit,
  copied with its tests from their repositories. Those services vendor fetchkit as it is and
  can't change in lockstep with it, so anything they rely on (the client's methods, the errors,
  the transport interface they implement) has to keep working. CI runs this as its own job
  before every release; run it before you push anything that changes a public interface.
- Runtime code imports only the standard library.
- Add a line to CHANGELOG.md for anything a caller would notice.
