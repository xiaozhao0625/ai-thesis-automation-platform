"""Executable ProjectFact P0-r4 candidate."""

from .extractor import extract_fixture_set
from .governance import build_review_payload

__all__ = ["build_review_payload", "extract_fixture_set"]
