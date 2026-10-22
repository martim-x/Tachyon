"""Данные представления диаграммы расходов по категориям (docs/03 §S10.1 T2).

Вход - точки доменной агрегации TT-26 (``SeriesPointDTO``), выход -
готовые столбцы для шаблона. Доли не пересчитываются: они уже посчитаны
одной pandas-агрегацией и дают в сумме 100.00% (NFR-3), здесь только
сворачивание топ-N в «Прочие» и форматирование из Decimal без float.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domains.forecasting.service import money
from app.domains.reporting.schemas import SeriesPointDTO

TOP_N: Final = 7
OTHER_LABEL: Final = "Прочие"

# Цветов ровно TOP_N: столько категорий реально держит столбчатая диаграмма
# (docs/03 §S10.1), каждый видимый столбец обязан получить свой цвет по
# позиции в порядке убывания доли, иначе легенда неоднозначна. Функция
# build_chart отклоняет top_n больше палитры.
SLICE_COLORS: Final = (
    "#2563eb",
    "#f59e0b",
    "#10b981",
    "#8b5cf6",
    "#ef4444",
    "#0ea5e9",
    "#84cc16",
)
OTHER_COLOR: Final = "#94a3b8"


def display_amount(value: Decimal) -> str:
    """Две цифры после запятой: деньги только на Decimal (docs/02)."""

    return f"{money(value):.2f}"


@dataclass(frozen=True, slots=True)
class ChartBar:
    """Один столбец диаграммы: подпись, цвет, сумма и доля из агрегации."""

    label: str
    color: str
    amount_display: str
    percent_display: str
    percent: Decimal
    is_other: bool = False


@dataclass(frozen=True, slots=True)
class ChartData:
    """Готовые данные для шаблона компонента диаграммы."""

    bars: tuple[ChartBar, ...]
    top_n: int
    has_other: bool
    total_display: str
    percent_total_display: str
    is_empty: bool


def build_chart(
    points: Sequence[SeriesPointDTO],
    *,
    top_n: int = TOP_N,
) -> ChartData:
    """Свернуть точки домена в столбцы; больше top_n - топ-N и «Прочие».

    Точки агрегации приходят упорядоченными по убыванию доли, поэтому
    порядок столбцов совпадает с порядком категорий в отчёте.
    """

    if top_n < 1:
        raise ValueError("top_n должен быть не меньше единицы")
    if top_n > len(SLICE_COLORS):
        raise ValueError(
            "top_n не может превышать размер палитры: столбцов больше цветов - дублируются"
        )

    rows = list(points)

    if not rows:
        return ChartData(
            bars=(),
            top_n=top_n,
            has_other=False,
            total_display=display_amount(Decimal("0.00")),
            percent_total_display=display_amount(Decimal("0.00")),
            is_empty=True,
        )

    visible = rows[:top_n]
    folded = rows[top_n:]

    bars = [
        ChartBar(
            label=row.category_name,
            color=SLICE_COLORS[index % len(SLICE_COLORS)],
            amount_display=display_amount(row.amount),
            percent_display=display_amount(row.share_percent),
            percent=money(row.share_percent),
        )
        for index, row in enumerate(visible)
    ]

    if folded:
        other_amount = sum((row.amount for row in folded), start=Decimal("0.00"))
        other_percent = sum((row.share_percent for row in folded), start=Decimal("0.00"))
        bars.append(
            ChartBar(
                label=OTHER_LABEL,
                color=OTHER_COLOR,
                amount_display=display_amount(other_amount),
                percent_display=display_amount(other_percent),
                percent=money(other_percent),
                is_other=True,
            )
        )

    total_amount = sum((row.amount for row in rows), start=Decimal("0.00"))
    total_percent = sum((row.share_percent for row in rows), start=Decimal("0.00"))

    return ChartData(
        bars=tuple(bars),
        top_n=top_n,
        has_other=bool(folded),
        total_display=display_amount(total_amount),
        percent_total_display=display_amount(total_percent),
        is_empty=False,
    )
