from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
import json
import math


class CanonicalJsonError(ValueError):
    """Raised when input cannot be represented as strict canonical JSON."""


def dumps_bytes(value: object) -> bytes:
    try:
        return _serialize(value).encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        if isinstance(exc, CanonicalJsonError):
            raise
        raise CanonicalJsonError(str(exc)) from exc


def loads_strict(payload: str | bytes) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise CanonicalJsonError(f"duplicate key: {key}")
            result[key] = value
        return result

    def reject_constant(token: str) -> object:
        raise CanonicalJsonError(f"invalid numeric constant: {token}")

    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8-sig")
        return json.loads(
            payload,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except CanonicalJsonError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalJsonError(str(exc)) from exc


def _serialize(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        _validate_string(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, Mapping):
        keys = list(value.keys())
        if not all(isinstance(key, str) for key in keys):
            raise CanonicalJsonError("object keys must be strings")
        for key in keys:
            _validate_string(key)
        ordered_keys = sorted(keys, key=_utf16_sort_key)
        return "{" + ",".join(
            f"{_serialize(key)}:{_serialize(value[key])}" for key in ordered_keys
        ) + "}"
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    raise CanonicalJsonError(f"unsupported JSON type: {type(value).__name__}")


def _validate_string(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalJsonError("strings must not contain lone surrogates")


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise CanonicalJsonError("JSON numbers must be finite")
    if value == 0:
        return "0"

    decimal_value = Decimal(repr(value))
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        fixed = format(decimal_value, "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed

    scientific = format(decimal_value.normalize(), "e")
    mantissa, exponent = scientific.split("e", 1)
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent_number = int(exponent)
    exponent_text = f"+{exponent_number}" if exponent_number >= 0 else str(
        exponent_number
    )
    return f"{mantissa}e{exponent_text}"
