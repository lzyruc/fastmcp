"""Tests for scalable JSON array uniqueness validation."""

from decimal import Decimal
from itertools import product
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

import fastmcp.utilities.json_schema_type as schema_module


@pytest.mark.parametrize("shape", ["integer", "object"])
def test_unique_array_does_not_scan_all_previous_items(
    monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    comparisons = 0
    original = schema_module._json_values_equal

    def counted(left: Any, right: Any) -> bool:
        nonlocal comparisons
        comparisons += 1
        return original(left, right)

    monkeypatch.setattr(schema_module, "_json_values_equal", counted)
    values = list(range(200)) if shape == "integer" else [{"id": i} for i in range(200)]
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {"type": shape},
                "uniqueItems": True,
            }
        )
    )
    result = adapter.validate_python(values)
    assert result == values
    assert type(result) is list
    # A deterministic work-count check, not a wall-clock speed threshold.
    assert comparisons <= len(values)


JSON_VALUES = [
    None,
    False,
    True,
    0,
    1,
    1.0,
    2,
    "",
    "1",
    "x",
    [],
    [1],
    [True],
    [1, False],
    [True, 0],
    {},
    {"x": 1},
    {"x": True},
    {"x": [1, False]},
    {"x": [True, 0]},
    {"x": 1, "y": 2},
    {"y": 2, "x": 1},
]


@pytest.mark.parametrize("left,right", list(product(JSON_VALUES, repeat=2)))
def test_uniqueness_preserves_json_equality(left: Any, right: Any) -> None:
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {},
                "uniqueItems": True,
            }
        )
    )
    duplicate = schema_module._json_values_equal(left, right)
    assert duplicate is not Draft202012Validator({"uniqueItems": True}).is_valid(
        [left, right]
    )
    if duplicate:
        with pytest.raises(ValidationError, match="Array items must be unique"):
            adapter.validate_python([left, right])
    else:
        result = adapter.validate_python([left, right])
        assert isinstance(result, list)
        assert result == [left, right]
        assert type(result[0]) is type(left)
        assert type(result[1]) is type(right)


def test_non_json_python_inputs_keep_existing_equality() -> None:
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {},
                "uniqueItems": True,
            }
        )
    )
    with pytest.raises(ValidationError, match="Array items must be unique"):
        adapter.validate_python([Decimal("1"), 1])
    nan = float("nan")
    assert adapter.validate_python([nan, nan]) == [nan, nan]


class UnhashableString(str):
    __hash__ = None


class UnhashableInt(int):
    __hash__ = None


@pytest.mark.parametrize(
    "value,other", [(UnhashableString("x"), "x"), (UnhashableInt(1), 1)]
)
@pytest.mark.parametrize("duplicate", [False, True])
def test_unhashable_scalar_subclasses_use_existing_equality(
    value: Any, other: Any, duplicate: bool
) -> None:
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {},
                "uniqueItems": True,
            }
        )
    )
    if duplicate:
        with pytest.raises(ValidationError, match="Array items must be unique"):
            adapter.validate_python([value, other])
    else:
        result = adapter.validate_python([value, None])
        assert isinstance(result, list)
        assert result[0] is value
        assert result[1] is None


def test_deeply_nested_values_fall_back_to_existing_equality() -> None:
    nested: Any = 0
    for _ in range(600):
        nested = [nested]
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {},
                "uniqueItems": True,
            }
        )
    )
    result = adapter.validate_python([0, nested])
    assert isinstance(result, list)
    assert result[0] == 0
    assert result[1] is nested


def test_single_python_cycle_needs_no_uniqueness_comparison() -> None:
    cycle: list[Any] = []
    cycle.append(cycle)
    adapter = TypeAdapter(
        schema_module.json_schema_to_type(
            {
                "type": "array",
                "items": {},
                "uniqueItems": True,
            }
        )
    )
    result = adapter.validate_python([cycle])
    assert isinstance(result, list)
    assert result[0] is cycle
