"""Data contracts.

The core stays stdlib-only, so contracts are validated by duck-typing:

* ``table``      – anything with ``.columns`` and ``.iloc`` (pandas / geopandas
                   DataFrames satisfy this)
* ``geodataframe`` – a table that also exposes ``.geometry`` (geopandas)
* ``series``     – anything with ``.iloc`` but no ``.columns``
* ``path``       – ``str`` / ``os.PathLike``
* ``any``        – no check

This lets plugins from different ecosystems talk to each other through the
same payload shape without the core depending on any of them.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence

from .errors import ContractError

TABLE = "table"
GEODATAFRAME = "geodataframe"
SERIES = "series"
PATH = "path"
ANY = "any"

KNOWN_TYPES = {TABLE, GEODATAFRAME, SERIES, PATH, ANY}


def type_name(obj: Any) -> str:
    """Best-effort contract type name for *obj*."""
    if hasattr(obj, "columns") and hasattr(obj, "iloc"):
        return GEODATAFRAME if hasattr(obj, "geometry") else TABLE
    if hasattr(obj, "iloc"):
        return SERIES
    if isinstance(obj, (str, os.PathLike)):
        return PATH
    return ANY


def describe_payload(payload: Any) -> Dict[str, str]:
    """Map payload keys to contract type names (for logging / CLI output)."""
    if isinstance(payload, dict):
        return {str(k): type_name(v) for k, v in payload.items()}
    return {"data": type_name(payload)}


def _check_value(key: str, value: Any, expected: str, errors: List[str]) -> None:
    actual = type_name(value)
    ok = {
        ANY: True,
        TABLE: actual in (TABLE, GEODATAFRAME),
        GEODATAFRAME: actual == GEODATAFRAME,
        SERIES: actual == SERIES,
        PATH: actual == PATH,
    }.get(expected)
    if ok is None:
        errors.append(
            f"{key}: unknown contract type {expected!r} (known: {sorted(KNOWN_TYPES)})"
        )
    elif not ok:
        errors.append(f"{key}: expected {expected!r}, got {actual!r}")


def validate_payload(
    payload: Any,
    contract: Dict[str, str],
    *,
    strict: bool = False,
    label: str = "input",
) -> List[str]:
    """Validate *payload* against *contract*; return a list of violations.

    With ``strict=True`` the payload must provide every contract key;
    otherwise missing keys are tolerated (plugins may compute defaults).
    """
    errors: List[str] = []
    if not contract:
        return errors
    if payload is None:
        if strict:
            errors.append(f"{label}: payload is None but contract requires {list(contract)}")
        return errors
    items = payload.items() if isinstance(payload, dict) else (("data", payload),)
    present = set()
    for key, value in items:
        present.add(key)
        expected = contract.get(key)
        if expected is not None:
            _check_value(key, value, expected, errors)
    if strict:
        for key in contract:
            if key not in present:
                errors.append(f"{label}: missing required key {key!r}")
    return errors


def enforce_payload(
    payload: Any,
    contract: Dict[str, str],
    *,
    strict: bool = False,
    label: str = "input",
) -> Any:
    """Validate and return *payload*; raise :class:`ContractError` on violations."""
    errors = validate_payload(payload, contract, strict=strict, label=label)
    if errors:
        raise ContractError("; ".join(errors))
    return payload


def to_rows(table: Any) -> List[Dict[str, Any]]:
    """Convert a table-like object to a list of row dicts (CLI/stdlib helper)."""
    if isinstance(table, Sequence) and not hasattr(table, "columns"):
        return [dict(row) for row in table]
    return [dict(zip(table.columns, row)) for row in table.iloc[:, :].values.tolist()]
