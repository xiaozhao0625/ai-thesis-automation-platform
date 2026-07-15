from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DomainConflict(ApplicationError):
    """A command conflicts with the persisted aggregate state."""


class ResourceNotFound(ApplicationError):
    """A requested aggregate does not exist."""


class ValidationFailure(ApplicationError):
    """A command is syntactically valid but violates an input boundary."""
