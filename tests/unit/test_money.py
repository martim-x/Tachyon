"""Деньги: Decimal с двумя знаками, ROUND_HALF_UP, целые копейки (docs/02 §Правила денег)."""

from decimal import Decimal

import pytest

from app.core.money import Money


def test_money_quantizes_to_two_places() -> None:
    assert Money("10.0") == Money("10.00")
    assert Money(10) == Money("10.00")
    assert repr(Money("25.50")) == "Money(25.50)"


def test_money_rounds_half_up() -> None:
    assert Money("25.505").amount == Decimal("25.51")
    assert Money("25.504").amount == Decimal("25.50")
    assert Money("-25.505").amount == Decimal("-25.51")


def test_money_cents_roundtrip() -> None:
    assert Money("25.50").to_cents() == 2550
    assert Money("0.10").to_cents() == 10
    assert Money.from_cents(2550) == Money("25.50")
    assert Money.from_cents(-100) == Money("-1.00")


def test_money_from_cents_requires_integer_cents() -> None:
    with pytest.raises(TypeError):
        Money.from_cents("2550")  # type: ignore[arg-type]


def test_money_rejects_inexact_constructor_types() -> None:
    with pytest.raises(TypeError):
        Money(25.5)  # type: ignore[arg-type]


def test_money_addition_and_subtraction_stay_quantized() -> None:
    assert Money("10.00") + Money("0.01") == Money("10.01")
    assert Money("10.00") - Money("25.50") == Money("-15.50")


def test_money_compares_with_decimal_string_and_int() -> None:
    assert Money("25.50") == Decimal("25.5")
    assert Money("25.50") == "25.50"
    assert Money("25.50") != 26
    assert Money("25.50") != "25.51"
