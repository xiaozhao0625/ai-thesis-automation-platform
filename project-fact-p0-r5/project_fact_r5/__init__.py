"""Executable ProjectFact P0-r5 candidate."""

from .extractor import extract_fixture_set
from .governance import build_review_payload, resolve_conflict_request

__all__ = ["build_review_payload", "extract_fixture_set", "resolve_conflict_request"]
