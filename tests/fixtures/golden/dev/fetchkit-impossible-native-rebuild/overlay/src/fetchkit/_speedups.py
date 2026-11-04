"""Picks the native accelerator (native/, Rust) when it is installed, else the pure-Python code.

``NATIVE_VERSION`` is the extension's version when it is active, and ``None`` otherwise.
"""

from __future__ import annotations

try:  # built into the environment by `maturin develop --release` in native/
    from fetchkit_native import __version__ as NATIVE_VERSION
    from fetchkit_native import encode_query
except ImportError:
    from fetchkit._query import encode_query

    NATIVE_VERSION = None

__all__ = ["NATIVE_VERSION", "encode_query"]
