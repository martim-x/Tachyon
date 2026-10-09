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


def test_money_compares_with_decimal_and_int_only() -> None:
    """Сравнение согласовано с hash и не бросает исключений на посторонних типах."""
    assert Money("25.50") == Decimal("25.5")
    assert Money("10.00") == 10
    assert Money("25.50") != 26
    # строки и прочие типы дают False, а не InvalidOperation
    assert Money("25.50") != "25.50"
    assert Money("1.00") != "abc"
    # контракт hash/eq для смешанных dict и set
    assert hash(Money("25.50")) == hash(Decimal("25.50"))
