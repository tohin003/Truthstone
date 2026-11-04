"""Intent Gateway — prompt to grounded TaskSpec (SPEC §9, §10)."""

from truthstone.intent.extractor import extract
from truthstone.intent.models import TaskSpec

__all__ = ["TaskSpec", "extract"]
