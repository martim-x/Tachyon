"""Юнит-тесты сборки данных диаграммы расходов (docs/03 §S10.1 T2).

Ожидаемые доли берутся из контракта агрегации TT-26: ``SeriesPointDTO``
уже содержит доли с двумя знаками, дающие в сумме 100.00
(test_reporting_api::test_by_category_shares_equal_one_hundred_percent),
поэтому здесь проверяется только свёртка топ-N в «Прочие», порядок,
цвета и форматирование из Decimal.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.reporting.schemas import SeriesPointDTO
from app.interface.dashboard.chart import (
    OTHER_COLOR,
    OTHER_LABEL,
    SLICE_COLORS,
    TOP_N,
    build_chart,
)

pytestmark = pytest.mark.unit


def point(name: str, amount: str, share: str) -> SeriesPointDTO:
    """Точка агрегации TT-26 в чистой минимальной форме."""

    return SeriesPointDTO(
        category_id=uuid4(),
        category_name=name,
        amount=Decimal(amount),
        share_percent=Decimal(share),
        limit_exceeded=False,
    )


def test_build_chart_empty_state_without_points() -> None:
    chart = build_chart([])

    assert chart.is_empty is True
    assert chart.bars == ()
    assert chart.total_display == "0.00"
    assert chart.percent_total_display == "0.00"


def test_build_chart_keeps_labels_amounts_and_share_order() -> None:
    points = [
        point("Продукты", "1250.00", "61.53"),
        point("Транспорт", "780.50", "38.47"),
    ]

    chart = build_chart(points)

    assert chart.is_empty is False
    assert chart.has_other is False
    assert [bar.label for bar in chart.bars] == ["Продукты", "Транспорт"]
    assert [bar.amount_display for bar in chart.bars] == ["1250.00", "780.50"]
    assert [bar.percent_display for bar in chart.bars] == ["61.53", "38.47"]
    assert [bar.percent for bar in chart.bars] == [Decimal("61.53"), Decimal("38.47")]
    assert chart.total_display == "2030.50"
    assert chart.percent_total_display == "100.00"


def test_build_chart_folds_more_than_seven_categories_into_other() -> None:
    # 8 категорий по 12.50% дают ровно 100.00%: топ-7 плюс «Прочие» тоже 12.50%.
    points = [
        point(f"Категория {index}", f"10.{index:02d}", "12.50")
        for index in range(1, 9)
    ]

    chart = build_chart(points)

    assert len(chart.bars) == TOP_N + 1
    assert chart.has_other is True

    other = chart.bars[-1]

    assert other.label == OTHER_LABEL
    assert other.is_other is True
    assert other.color == OTHER_COLOR
    assert other.amount_display == "10.08"
    assert other.percent_display == "12.50"

    assert [bar.color for bar in chart.bars[:-1]] == list(SLICE_COLORS)

    total_percent = sum(
        (Decimal(bar.percent_display) for bar in chart.bars),
        start=Decimal("0.00"),
    )

    assert total_percent == Decimal("100.00")


def test_build_chart_seven_categories_fit_without_other() -> None:
    shares = ("20.00", "18.00", "16.00", "14.00", "12.00", "10.00", "10.00")
    points = [point(f"Категория {index}", "10.00", shares[index]) for index in range(7)]

    chart = build_chart(points)

    assert chart.has_other is False
    assert len(chart.bars) == TOP_N
    assert all(bar.is_other is False for bar in chart.bars)


def test_build_chart_top_n_parameter_folds_earlier() -> None:
    points = [
        point("Первая", "40.00", "40.00"),
        point("Вторая", "30.00", "30.00"),
        point("Третья", "20.00", "20.00"),
        point("Четвёртая", "10.00", "10.00"),
    ]

    chart = build_chart(points, top_n=2)

    assert [bar.label for bar in chart.bars] == ["Первая", "Вторая", OTHER_LABEL]

    other = chart.bars[-1]

    assert other.is_other is True
    assert other.amount_display == "30.00"
    assert other.percent_display == "30.00"
    assert chart.percent_total_display == "100.00"


def test_build_chart_assigns_colors_by_share_position() -> None:
    points = [
        point("Первая", "10.00", "50.00"),
        point("Вторая", "6.00", "30.00"),
        point("Третья", "4.00", "20.00"),
    ]

    chart = build_chart(points)

    assert [bar.color for bar in chart.bars] == list(SLICE_COLORS[:3])


def test_build_chart_rejects_non_positive_top_n() -> None:
    with pytest.raises(ValueError):
        build_chart([point("Продукты", "10.00", "100.00")], top_n=0)


def test_build_chart_rejects_top_n_beyond_color_palette() -> None:
    # Цвет обязан быть уникальным на столбец (легенда неоднозначна иначе),
    # поэтому top_n больше палитры отклоняется, повторение недопустимо.
    points = [
        point(f"Категория {index}", "10.00", "12.50")
        for index in range(8)
    ]

    with pytest.raises(ValueError):
        build_chart(points, top_n=len(points))

    with pytest.raises(ValueError):
        build_chart(points, top_n=100)
