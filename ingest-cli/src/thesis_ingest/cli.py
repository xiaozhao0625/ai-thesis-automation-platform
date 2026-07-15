from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

from thesis_ingest.config import ConfigError
from thesis_ingest.pipeline import PipelineError, ScanInterrupted, run_scan
from thesis_ingest.verification import VerificationError, verify_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m thesis_ingest")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="scan one controlled source mount")
    scan.add_argument("--config", required=True, type=Path)
    scan.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="verify a completed ingest output")
    verify.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "scan":
            result = run_scan(
                arguments.config,
                cli_output=arguments.output,
            )
            print(
                json.dumps(
                    {
                        "status": result.status,
                        "output": str(result.output_path),
                        "resumed_from_checkpoint": result.resumed_from_checkpoint,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        report = verify_package(arguments.manifest)
        print(
            json.dumps(
                {
                    "verified": True,
                    "status": report.status,
                    "file_count": report.file_count,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 3 if _is_source_safety_error(str(exc)) else 2
    except ScanInterrupted as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 5
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 3 if "SOURCE_MUTATED_DURING_SCAN" in str(exc) else exc.exit_code
    except Exception as exc:
        print(f"INTERNAL_ERROR: {exc}", file=sys.stderr)
        return 10


def _is_source_safety_error(message: str) -> bool:
    return any(
        code in message
        for code in (
            "SOURCE_ROOT_NOT_FOUND",
            "UNSUPPORTED_ROOT_URI",
            "UNSUPPORTED_MOUNT_TYPE",
            "OUTPUT_INSIDE_SOURCE_ROOT",
        )
    )
