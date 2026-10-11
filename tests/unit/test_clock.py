"""Часы: FrozenClock фиксирует время, SystemClock читает системное (docs/02 §«Ядро»)."""

from datetime import UTC, date, datetime, timedelta

from app.core.clock import FrozenClock, SystemClock


def test_frozen_clock_keeps_its_day() -> None:
    clock = FrozenClock("2026-10-15")
    assert clock.today() == date(2026, 10, 15)
    assert clock.now() == datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_frozen_clock_accepts_date_object() -> None:
    clock = FrozenClock(date(2027, 3, 1))
    assert clock.today() == date(2027, 3, 1)
    assert clock.now().date() == date(2027, 3, 1)


def test_frozen_clock_time_does_not_move() -> None:
    clock = FrozenClock("2026-10-15")
    assert clock.now() == clock.now()


def test_system_clock_returns_aware_utc_moment() -> None:
    moment = SystemClock().now()
    assert moment.tzinfo is not None
    assert abs(moment - datetime.now(UTC)) < timedelta(seconds=60)


def test_system_clock_today_is_current_date() -> None:
    # Полночь может перескочить между двумя вызовами - допускаем сутки разницы.
    delta = abs(SystemClock().today() - datetime.now(UTC).date())
    assert delta <= timedelta(days=1)
