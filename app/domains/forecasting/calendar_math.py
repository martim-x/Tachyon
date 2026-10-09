"""Календарная математика прогноза (docs/06 §Формулы; решение 8 в docs/00 §4)."""

import calendar
from datetime import date


def days_in_month(year: int, month: int) -> int:
    """Единственный источник правды о длине месяца: 28, 29, 30 или 31.

    calendar.monthrange знает про високосный год; timedelta(days=30) и
    захардкоженные константы здесь ошибка (docs/02 §«Формулы»).
    """
    return calendar.monthrange(year, month)[1]


def days_elapsed(year: int, month: int, as_of: date) -> int:
    """Прошедшие дни отчётного месяца на дату as_of.

    Месяц ещё не начался - ноль прошедших дней, делить не на что
    (решение 8: сравнение с началом месяца, а не взятие as_of.day).
    Месяц уже закрыт (as_of в одном из следующих месяцев) - полная длина:
    месяц завершён, projected равен тратам (docs/03 §S6.1).
    Внутри месяца - as_of.day, отсечённый длиной месяца.
    """
    if as_of < date(year, month, 1):
        return 0
    if (as_of.year, as_of.month) > (year, month):
        return days_in_month(year, month)
    return min(as_of.day, days_in_month(year, month))
