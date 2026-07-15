from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

import app.db.models  # noqa: F401 - registers all mapped tables on Base.metadata
from app.db.base import Base


def collect_snapshot(session: Session, artifact_root: Path) -> dict[str, object]:
    revision = session.execute(text("select version_num from alembic_version")).scalar_one()
    table_counts = {
        table.name: int(session.scalar(select(func.count()).select_from(table)) or 0)
        for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name)
    }
    files = []
    if artifact_root.is_dir():
        files = [
            path
            for path in artifact_root.rglob("*")
            if path.is_file()
            and (path.relative_to(artifact_root).parts or (None,))[0] != ".staging"
        ]
    return {
        "alembic_revision": str(revision),
        "table_counts": table_counts,
        "artifact_store": {
            "file_count": len(files),
            "size_bytes": sum(path.stat().st_size for path in files),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print database and Artifact Store counts for a handoff bundle"
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args(argv)

    engine = create_engine(args.database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as session:
            snapshot = collect_snapshot(session, args.artifact_root)
    finally:
        engine.dispose()
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
