"""Единая pandas-агрегация для API, экспорта и диаграмм."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import pandas as pd

MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")
HUNDRED_PERCENT = Decimal("100.00")
UNCATEGORIZED_KEY = "__uncategorized__"
UNCATEGORIZED_NAME = "Без категории"

FRAME_COLUMNS = (
    "category_key",
    "kind",
    "amount_cents",
)


@dataclass(frozen=True, slots=True)
class ReportRow:
    """Одна строка выборки, подготовленная reporting-репозиторием."""

    category_id: UUID | None
    category_name: str | None
    kind: str
    amount_cents: int
    limit_cents: int | None = None


@dataclass(frozen=True, slots=True)
class CategoryAggregate:
    """Итог расходов одной категории."""

    category_id: UUID | None
    category_name: str
    amount: Decimal
    share_percent: Decimal
    limit: Decimal | None
    limit_remaining: Decimal | None
    limit_percent: Decimal | None
    limit_exceeded: bool


@dataclass(frozen=True, slots=True)
class ReportAggregate:
    """Общий результат одной агрегации."""

    income: Decimal
    expense: Decimal
    balance: Decimal
    categories: tuple[CategoryAggregate, ...]


def money_from_cents(cents: int) -> Decimal:
    """Преобразовать целые копейки в Decimal с двумя знаками."""

    return (Decimal(cents) / Decimal(100)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def percent(numerator: int, denominator: int) -> Decimal:
    """Посчитать процент без float."""

    if denominator <= 0:
        return Decimal("0.00")

    return (Decimal(numerator) * HUNDRED_PERCENT / Decimal(denominator)).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def aggregate_report(rows: Iterable[ReportRow]) -> ReportAggregate:
    """Построить сводку одним pandas-проходом.

    Категорийные доли считаются только по расходам. После округления
    остаток добавляется крупнейшей категории, поэтому сумма всегда 100.00%.
    """

    source_rows = list(rows)

    category_names: dict[str, str] = {}
    category_limits: dict[str, int | None] = {}
    records: list[dict[str, str | int]] = []

    for row in source_rows:
        if row.kind not in {"income", "expense"}:
            raise ValueError(f"Неизвестный вид операции: {row.kind}")

        if isinstance(row.amount_cents, bool) or not isinstance(
            row.amount_cents,
            int,
        ):
            raise TypeError("amount_cents должен быть целым числом")

        category_key = str(row.category_id) if row.category_id is not None else UNCATEGORIZED_KEY
        category_name = row.category_name or UNCATEGORIZED_NAME

        category_names[category_key] = category_name
        category_limits[category_key] = row.limit_cents
        records.append(
            {
                "category_key": category_key,
                "kind": row.kind,
                "amount_cents": row.amount_cents,
            }
        )

    frame = pd.DataFrame.from_records(
        records,
        columns=FRAME_COLUMNS,
    )

    if frame.empty:
        return ReportAggregate(
            income=Decimal("0.00"),
            expense=Decimal("0.00"),
            balance=Decimal("0.00"),
            categories=(),
        )

    income_cents = int(
        frame.loc[
            frame["kind"] == "income",
            "amount_cents",
        ].sum()
    )
    expense_cents = int(
        frame.loc[
            frame["kind"] == "expense",
            "amount_cents",
        ].sum()
    )

    expense_frame = frame.loc[frame["kind"] == "expense"]

    if expense_frame.empty:
        return ReportAggregate(
            income=money_from_cents(income_cents),
            expense=Decimal("0.00"),
            balance=money_from_cents(income_cents),
            categories=(),
        )

    grouped_frame = expense_frame.groupby(
        "category_key",
        as_index=False,
        sort=True,
    )["amount_cents"].sum()

    grouped_values = [
        (str(row.category_key), int(row.amount_cents))
        for row in grouped_frame.itertuples(index=False)
    ]
    grouped_values.sort(
        key=lambda item: (
            -item[1],
            category_names[item[0]],
        )
    )

    rounded_shares = {
        category_key: percent(amount_cents, expense_cents)
        for category_key, amount_cents in grouped_values
    }

    rounding_difference = HUNDRED_PERCENT - sum(
        rounded_shares.values(),
        start=Decimal("0.00"),
    )
    if grouped_values:
        largest_category_key = grouped_values[0][0]
        rounded_shares[largest_category_key] += rounding_difference

    categories: list[CategoryAggregate] = []

    for category_key, amount_cents in grouped_values:
        limit_cents = category_limits.get(category_key)
        amount = money_from_cents(amount_cents)

        if limit_cents is None:
            limit = None
            limit_remaining = None
            limit_percent = None
            limit_exceeded = False
        else:
            limit = money_from_cents(limit_cents)
            limit_remaining = money_from_cents(limit_cents - amount_cents)
            limit_percent = percent(amount_cents, limit_cents)
            limit_exceeded = amount_cents >= limit_cents

        categories.append(
            CategoryAggregate(
                category_id=(None if category_key == UNCATEGORIZED_KEY else UUID(category_key)),
                category_name=category_names[category_key],
                amount=amount,
                share_percent=rounded_shares[category_key],
                limit=limit,
                limit_remaining=limit_remaining,
                limit_percent=limit_percent,
                limit_exceeded=limit_exceeded,
            )
        )

    income = money_from_cents(income_cents)
    expense = money_from_cents(expense_cents)

    return ReportAggregate(
        income=income,
        expense=expense,
        balance=(income - expense).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        ),
        categories=tuple(categories),
    )
