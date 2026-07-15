from __future__ import annotations

import math

import pytest

from thesis_ingest.canonical_json import CanonicalJsonError, dumps_bytes, loads_strict


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b": 1, "a": "中文"}, b'{"a":"\xe4\xb8\xad\xe6\x96\x87","b":1}'),
        ({"value": -0.0}, b'{"value":0}'),
        ({"value": 1.0}, b'{"value":1}'),
        ({"value": 1e-7}, b'{"value":1e-7}'),
        ({"value": 1e-6}, b'{"value":0.000001}'),
        ({"value": 1e20}, b'{"value":100000000000000000000}'),
        ({"value": 1e21}, b'{"value":1e+21}'),
    ],
)
def test_dumps_bytes_uses_stable_canonical_encoding(
    value: object, expected: bytes
) -> None:
    assert dumps_bytes(value) == expected


def test_object_keys_follow_utf16_code_unit_order() -> None:
    value = {"\U00010000": 1, "\ue000": 2}

    assert dumps_bytes(value) == (
        b'{"\xf0\x90\x80\x80":1,"\xee\x80\x80":2}'
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CanonicalJsonError, match="finite"):
        dumps_bytes({"value": value})


def test_duplicate_object_keys_are_rejected_on_load() -> None:
    with pytest.raises(CanonicalJsonError, match="duplicate key"):
        loads_strict('{"same":1,"same":2}')


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_numeric_tokens_are_rejected_on_load(token: str) -> None:
    with pytest.raises(CanonicalJsonError, match="invalid numeric constant"):
        loads_strict('{"value":' + token + "}")


def test_loaded_json_can_be_reencoded_without_a_bom_or_trailing_newline() -> None:
    loaded = loads_strict(b'{"z":2,"a":[true,null,"x"]}')

    assert dumps_bytes(loaded) == b'{"a":[true,null,"x"],"z":2}'
