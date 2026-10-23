"""Unit-тесты PDF-адаптера: формат денег, структура файла (docs/03 §S7.2)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.reporting.schemas import ReportDTO, SeriesPointDTO
from app.interface.export.pdf import (
    build_pdf_report,
    format_money,
    format_percent,
    report_file_name,
)

pytestmark = pytest.mark.unit


def _sample_report() -> ReportDTO:
    return ReportDTO(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        income=Decimal("2000.07"),
        expense=Decimal("150.34"),
        balance=Decimal("1849.73"),
        categories=[
            SeriesPointDTO(
                category_id=None,
                category_name="Продукты",
                amount=Decimal("100.13"),
                share_percent=Decimal("66.64"),
                limit=Decimal("120.07"),
                limit_remaining=Decimal("19.94"),
                limit_percent=Decimal("83.36"),
                limit_exceeded=False,
            ),
            SeriesPointDTO(
                category_id=None,
                category_name="Транспорт",
                amount=Decimal("50.21"),
                share_percent=Decimal("33.36"),
                limit=None,
                limit_remaining=None,
                limit_percent=None,
                limit_exceeded=False,
            ),
        ],
        forecast=Decimal("310.99"),
        forecast_month="2026-10",
    )


def test_format_money_renders_string_with_two_places() -> None:
    assert format_money(Decimal("2000.00")) == "2000.00"
    assert format_money(Decimal("0.101")) == "0.10"
    assert format_money(Decimal("1.005")) == "1.01"
    assert format_money(Decimal("-749.50")) == "-749.50"


def test_format_percent_renders_string_with_two_places() -> None:
    assert format_percent(Decimal("33.3333")) == "33.33"
    assert format_percent(Decimal("100")) == "100.00"
    assert format_percent(Decimal("7")) == "7.00"


def test_format_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        format_money(150.0)  # type: ignore[arg-type]


def test_report_file_name_includes_period() -> None:
    assert report_file_name(date(2026, 10, 1), date(2026, 10, 31)) == (
        "report-20261001-20261031.pdf"
    )


def test_build_pdf_report_returns_pdf_structure() -> None:
    payload = build_pdf_report(_sample_report())

    assert payload.startswith(b"%PDF-")
    assert payload.rstrip().endswith(b"%%EOF")
    assert b"/Type /Page" in payload


def test_build_pdf_report_renders_money_as_exact_strings() -> None:
    payload = build_pdf_report(_sample_report())

    # Файл собирается без компрессии контента: суммы лежат в потоках
    # как точные строки из Decimal, а не float-представление.
    for amount in (b"2000.07", b"150.34", b"1849.73", b"310.99", b"100.13", b"50.21"):
        assert amount in payload


def test_build_pdf_report_wraps_long_category_names() -> None:
    """Имя категории ~100 символов: Paragraph переносит, файл собирается."""
    long_name = "Очень" * 20
    report = ReportDTO(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        income=Decimal("0.00"),
        expense=Decimal("12.34"),
        balance=Decimal("-12.34"),
        categories=[
            SeriesPointDTO(
                category_id=None,
                category_name=long_name,
                amount=Decimal("8.94"),
                share_percent=Decimal("72.45"),
                limit=None,
                limit_remaining=None,
                limit_percent=None,
                limit_exceeded=False,
            ),
            SeriesPointDTO(
                category_id=None,
                category_name="A & B «<b>жирный</b>»",
                amount=Decimal("3.40"),
                share_percent=Decimal("27.55"),
                limit=None,
                limit_remaining=None,
                limit_percent=None,
                limit_exceeded=False,
            ),
        ],
        forecast=Decimal("0.00"),
        forecast_month="2026-10",
    )

    payload = build_pdf_report(report)

    assert payload.startswith(b"%PDF-")
    assert payload.rstrip().endswith(b"%%EOF")
    assert b"8.94" in payload
    assert b"3.40" in payload


def test_build_pdf_report_empty_period_still_builds() -> None:
    report = ReportDTO(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        income=Decimal("0.00"),
        expense=Decimal("0.00"),
        balance=Decimal("0.00"),
        categories=[],
        forecast=Decimal("0.00"),
        forecast_month="2026-10",
    )

    payload = build_pdf_report(report)

    assert payload.startswith(b"%PDF-")
    assert b"0.00" in payload
