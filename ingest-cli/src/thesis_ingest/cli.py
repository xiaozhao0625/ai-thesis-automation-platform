from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m thesis_ingest")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scan", help="scan one controlled source mount")
    commands.add_parser("verify", help="verify a completed ingest output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
