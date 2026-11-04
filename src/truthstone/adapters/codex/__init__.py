"""Codex adapter: translation, the command-hook forwarder, the installer and the plugin.

Deliberately empty of imports: ``truthstone.adapters.codex.hook`` runs on every Codex tool
call and must not pay for pydantic/fastapi transitively. See ``docs/CODEX.md``.
"""
