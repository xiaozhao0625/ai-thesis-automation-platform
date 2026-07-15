from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path


class HashingError(OSError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.content_hash: None = None
        super().__init__(f"{code}: {message}")


class FileChangedDuringHash(HashingError):
    pass


@dataclass(frozen=True)
class HashResult:
    content_hash: str
    size_bytes: int
    modified_time_ns: int
    bytes_read: int


def hash_file(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
    progress: Callable[[int], None] | None = None,
) -> HashResult:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    try:
        before = path.stat()
        digest = hashlib.sha256()
        bytes_read = 0
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
                bytes_read += len(chunk)
                if progress is not None:
                    progress(bytes_read)
        after = path.stat()
    except FileChangedDuringHash:
        raise
    except OSError as exc:
        raise HashingError("HASH_READ_FAILED", str(exc)) from exc

    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or bytes_read != before.st_size
    ):
        raise FileChangedDuringHash(
            "FILE_CHANGED_DURING_SCAN",
            (
                f"metadata changed while hashing {path.name}: "
                f"size {before.st_size}->{after.st_size}, "
                f"mtime {before.st_mtime_ns}->{after.st_mtime_ns}"
            ),
        )
    return HashResult(
        content_hash="sha256:" + digest.hexdigest(),
        size_bytes=after.st_size,
        modified_time_ns=after.st_mtime_ns,
        bytes_read=bytes_read,
    )
