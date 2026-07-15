from __future__ import annotations

import hashlib
import re

from thesis_ingest.canonical_json import dumps_bytes


def extract_reference_candidates(
    text: str,
    *,
    source_ingest_record_id: str,
    scan_id: str,
    created_at: str,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    first_by_text: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        raw_reference = raw_line.strip()
        if not raw_reference:
            continue
        candidate_id = _stable_id(
            {
                "line_number": line_number,
                "raw_reference_text": raw_reference,
                "scan_id": scan_id,
                "source_ingest_record_id": source_ingest_record_id,
            }
        )
        candidate: dict[str, object] = {
            "schema_version": "0.1",
            "record_type": "REFERENCE_CANDIDATE",
            "reference_candidate_id": candidate_id,
            "scan_id": scan_id,
            "raw_reference_text": raw_reference,
            "source_ingest_record_id": source_ingest_record_id,
            "source_locator": {
                "locator_type": "LINE_RANGE",
                "line_start": line_number,
                "line_end": line_number,
            },
            "extraction_method": "PLAIN_TEXT_LINE",
            "verification_status": "UNVERIFIED",
            "relevance_status": "UNKNOWN",
            "license_status": "UNKNOWN",
            "issue_refs": [],
            "created_at": created_at,
        }

        doi_match = re.search(r"10\.\d{4,9}/[^\s]+", raw_reference, re.I)
        if doi_match:
            candidate["doi_candidate"] = doi_match.group(0).rstrip(".,;)]}")
        url_match = re.search(r"https?://[^\s]+", raw_reference, re.I)
        if url_match:
            candidate["url_candidate"] = url_match.group(0).rstrip(".,;)]}")
        year_match = re.search(r"(?<!\d)(1\d{3}|20\d{2}|2[1-9]\d{2})(?!\d)", raw_reference)
        if year_match:
            candidate["year_candidate"] = int(year_match.group(1))

        clean = re.sub(r"https?://[^\s]+", "", raw_reference, flags=re.I)
        clean = re.sub(r"(?:doi\s*:\s*)?10\.\d{4,9}/[^\s]+", "", clean, flags=re.I)
        clean = re.sub(r"^\s*\[?\d+\]?\s*[.、]?\s*", "", clean)
        parts = [part.strip(" ,;[]()") for part in clean.split(".") if part.strip(" ,;[]()")]
        non_year_parts = [
            part for part in parts if not re.fullmatch(r"(?:1\d{3}|2\d{3})", part)
        ]
        if len(non_year_parts) >= 2:
            candidate["author_candidates"] = [non_year_parts[0]]
            candidate["title_candidate"] = non_year_parts[1]

        previous = first_by_text.get(raw_reference)
        if previous is not None:
            candidate["duplicate_of"] = previous
        else:
            first_by_text[raw_reference] = candidate_id

        parsed_fields = {
            "title_candidate",
            "author_candidates",
            "year_candidate",
            "doi_candidate",
            "isbn_candidate",
            "url_candidate",
        }
        if not parsed_fields.intersection(candidate):
            issue_id = _stable_id(
                {
                    "code": "REFERENCE_CLUE_UNPARSED",
                    "reference_candidate_id": candidate_id,
                    "scan_id": scan_id,
                }
            )
            candidate["issue_refs"] = [issue_id]
        candidates.append(candidate)
    return candidates


def _stable_id(projection: object) -> str:
    return "sha256:" + hashlib.sha256(dumps_bytes(projection)).hexdigest()
