from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.core.errors import ValidationFailure


class ControlledSourceResolver:
    def __init__(
        self,
        *,
        platform_root: Path,
        allowed_roots: list[Path],
        artifact_store_root: Path,
    ) -> None:
        self.platform_root = platform_root.resolve()
        self.allowed_roots = [path.resolve() for path in allowed_roots]
        self.artifact_store_root = artifact_store_root.resolve()

    def resolve(self, configured_path: str) -> Path:
        normalized = configured_path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or _looks_like_windows_absolute(normalized)
            or normalized.startswith("//")
        ):
            raise ValidationFailure(
                "SOURCE_PATH_NOT_ALLOWED",
                "source path must be a controlled project-relative path",
            )
        candidate = (self.platform_root / Path(*pure.parts)).resolve()
        if candidate.is_relative_to(self.artifact_store_root):
            raise ValidationFailure(
                "SOURCE_PATH_NOT_ALLOWED", "artifact store cannot be scanned"
            )
        if not any(candidate.is_relative_to(root) for root in self.allowed_roots):
            raise ValidationFailure(
                "SOURCE_PATH_NOT_ALLOWED", "source path is outside configured roots"
            )
        if not candidate.is_dir():
            raise ValidationFailure(
                "SOURCE_PATH_NOT_FOUND", "source directory does not exist"
            )
        return candidate


def _looks_like_windows_absolute(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"
