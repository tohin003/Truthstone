# Vendored modules

datapipe has no runtime dependencies, so the few third-party modules it needs are copied here
verbatim from an upstream release:

| module | upstream release | file |
|--------|------------------|------|
| isostamp | 1.2.0 | `isostamp.py` |

These files are never edited in this repository: they must stay byte-for-byte what upstream
ships, so that an upgrade is a plain copy of the next release and a security fix can be checked
against upstream at a glance. Anything datapipe needs beyond what a vendored module offers goes
in datapipe's own code.
