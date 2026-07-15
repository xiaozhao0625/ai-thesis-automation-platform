from __future__ import annotations


def can_support_success_claim(result: dict[str, object]) -> bool:
    return (
        result.get("provenance_type") == "TRUSTED_EXECUTION"
        and result.get("verification_status") == "VERIFIED"
        and result.get("status") == "SUCCEEDED"
        and isinstance(result.get("execution_fingerprint"), str)
        and isinstance(result.get("node_execution_attempt_id"), str)
    )
