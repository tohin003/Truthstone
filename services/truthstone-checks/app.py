"""Entry point for hosts that load ``app.py:app`` (Vercel's Python runtime)."""

from truthstone_checks import app

__all__ = ["app"]
