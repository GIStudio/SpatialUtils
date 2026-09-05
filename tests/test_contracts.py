from __future__ import annotations

import pytest

from spatialharness.core import ContractError, enforce_payload, validate_payload
from spatialharness.core.contracts import describe_payload, type_name


class FakeDataFrame(dict):
    """最小 duck-type：pandas DataFrame 只需 columns + iloc 即可通过 table 检查。"""


class _Has:
    def __init__(self, *attrs):
        for a in attrs:
            setattr(self, a, None)


def test_type_name_duck_typing():
    assert type_name(_Has("columns", "iloc")) == "table"
    assert type_name(_Has("columns", "iloc", "geometry")) == "geodataframe"
    assert type_name(_Has("iloc")) == "series"
    assert type_name("D:/data") == "path"
    assert type_name(42) == "any"


def test_validate_table_payload():
    contract = {"data": "table"}
    assert validate_payload({"data": _Has("columns", "iloc")}, contract) == []
    errors = validate_payload({"data": "not a table"}, contract)
    assert errors and "expected 'table'" in errors[0]


def test_validate_missing_keys_strict():
    contract = {"a": "any", "b": "any"}
    errors = validate_payload({"a": 1}, contract, strict=True)
    assert any("missing" in e for e in errors)
    assert validate_payload({"a": 1}, contract, strict=False) == []


def test_enforce_raises():
    with pytest.raises(ContractError):
        enforce_payload({"data": 3.14}, {"data": "table"})


def test_none_payload_tolerated_when_not_strict():
    assert validate_payload(None, {"data": "table"}) == []
    errs = validate_payload(None, {"data": "table"}, strict=True)
    assert errs


def test_unknown_contract_type_flagged():
    errors = validate_payload({"x": 1}, {"x": " dataframee"})
    assert errors and "unknown contract type" in errors[0]


def test_describe_payload_non_dict():
    assert describe_payload(_Has("columns", "iloc")) == {"data": "table"}
