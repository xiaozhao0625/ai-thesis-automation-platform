from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .extractor import extract_fixture_set
from .governance import build_review_payload, resolve_conflict_request


def main() -> None:
    parser = argparse.ArgumentParser(description="ProjectFact P0-r6 executable candidate")
    parser.add_argument("command", choices=["extract", "build-review-payload", "resolve-conflict"])
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--conflicting-source", action="store_true")
    args = parser.parse_args()

    if args.command == "extract":
        result = {"observations": extract_fixture_set(args.fixtures, conflicting_source=args.conflicting_source)}
    elif args.command == "resolve-conflict":
        try:
            request = json.load(sys.stdin)
        except json.JSONDecodeError as error:
            parser.error(f"resolve-conflict requires a JSON request body on stdin: {error.msg}")
        result = resolve_conflict_request(args.fixtures, request)
    else:
        result = build_review_payload(args.fixtures)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
