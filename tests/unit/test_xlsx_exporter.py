"""Unit-тесты xlsx-адаптера порта экспорта (docs/02 §export, docs/03 §S7.1).

Без БД и сети: DTO собираются вручную. Проверяются три листа, русские
шапки, числовые денежные ячейки на Decimal (не float, не текст),
имя файла с периодом и поведение пустого периода.

Числа перечитываются из xlsx как int/float, поэтому сравнение идёт
через Decimal(str(значение)) - это проверка значения, а не типа
хранения;.Decimal появляется на стороне записи (виден в адаптере).
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID

import pytest
from openpyxl import load_workbook

from app.domains.reporting.schemas import ExportOperationDTO, ExportReportDTO, SeriesPointDTO
from app.interface.export.base import ExportFile
from app.interface.export.xlsx import (
    CATEGORIES_HEADERS,
    CATEGORIES_WIDTHS,
    MONEY_CELL_FORMAT,
    OPERATIONS_HEADERS,
    OPERATIONS_WIDTHS,
    PERCENT_CELL_FORMAT,
    SUMMARY_WIDTHS,
    XLSX_MEDIA_TYPE,
    XlsxReportExporter,
)

pytestmark = pytest.mark.unit

FOOD_ID = UUID("10000000-0000-0000-0000-000000000001")


def _sample_report() -> ExportReportDTO:
    return ExportReportDTO(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        income=Decimal("2000.00"),
        expense=Decimal("150.00"),
        balance=Decimal("1850.00"),
        operations=[
            ExportOperationDTO(
                occurred_on=date(2026, 10, 1),
                category_name="Зарплата",
                kind="income",
                amount=Decimal("2000.00"),
            ),
            ExportOperationDTO(
                occurred_on=date(2026, 10, 5),
                category_name="Продукты",
                kind="expense",
                amount=Decimal("100.00"),
            ),
        ],
        categories=[
            SeriesPointDTO(
                category_id=FOOD_ID,
                category_name="Продукты",
                amount=Decimal("100.00"),
                share_percent=Decimal("66.67"),
                limit=Decimal("120.00"),
                limit_remaining=Decimal("20.00"),
                limit_percent=Decimal("83.33"),
                limit_exceeded=False,
            ),
            SeriesPointDTO(
                category_id=None,
                category_name="Без категории",
                amount=Decimal("50.00"),
                share_percent=Decimal("33.33"),
                limit=None,
                limit_remaining=None,
                limit_percent=None,
                limit_exceeded=False,
            ),
        ],
    )


def _empty_report() -> ExportReportDTO:
    return ExportReportDTO(
        date_from=date(2026, 10, 25),
        date_to=date(2026, 11, 20),
        income=Decimal("0.00"),
        expense=Decimal("0.00"),
        balance=Decimal("0.00"),
        operations=[],
        categories=[],
    )


def _loaded(value: object) -> str:
    """Дата/число перечитанного ввода в виде ISO-префикса."""

    return str(value)[:10]


def _reloaded(number: object) -> Decimal:
    """Точное сравнение числа, перечитанного из xlsx (int/float)."""

    return Decimal(str(number))


def test_export_writes_three_sheets_with_russian_headers() -> None:
    file = XlsxReportExporter().export(_sample_report())
    workbook = load_workbook(BytesIO(file.content))

    assert workbook.sheetnames == ["Операции", "По категориям", "Сводка"]

    operations = workbook["Операции"]
    assert [cell.value for cell in operations[1][: len(OPERATIONS_HEADERS)]] == list(
        OPERATIONS_HEADERS
    )
    assert operations["A1"].font.bold is True

    categories = workbook["По категориям"]
    assert [cell.value for cell in categories[1][: len(CATEGORIES_HEADERS)]] == list(
        CATEGORIES_HEADERS
    )

    summary = workbook["Сводка"]
    assert summary["A3"].value == "Доходы"
    assert summary["A4"].value == "Расходы"
    assert summary["A5"].value == "Баланс"


def test_export_writes_operations_rows_with_money_cells() -> None:
    file = XlsxReportExporter().export(_sample_report())
    workbook = load_workbook(BytesIO(file.content))
    sheet = workbook["Операции"]

    assert sheet.max_row == 3  # шапка + две операции

    first = sheet[2]
    assert _loaded(first[0].value) == "2026-10-01"
    assert first[1].value == "Зарплата"
    assert first[2].value == "Доход"
    assert _reloaded(first[3].value) == Decimal("2000.00")
    assert first[3].number_format == MONEY_CELL_FORMAT

    second = sheet[3]
    assert second[2].value == "Расход"
    assert _reloaded(second[3].value) == Decimal("100.00")
    assert second[3].number_format == MONEY_CELL_FORMAT


def test_export_categories_rows_and_column_widths() -> None:
    file = XlsxReportExporter().export(_sample_report())
    workbook = load_workbook(BytesIO(file.content))

    operations = workbook["Операции"]
    assert operations.column_dimensions["A"].width == OPERATIONS_WIDTHS[0]
    assert operations.column_dimensions["D"].width == OPERATIONS_WIDTHS[3]

    categories = workbook["По категориям"]
    assert categories.column_dimensions["B"].width == CATEGORIES_WIDTHS[1]
    assert categories.max_row == 3  # шапка + две категории

    food = categories[2]
    assert food[0].value == "Продукты"
    assert _reloaded(food[1].value) == Decimal("100.00")
    assert food[1].number_format == MONEY_CELL_FORMAT
    assert _reloaded(food[2].value) == Decimal("66.67")
    assert food[2].number_format == PERCENT_CELL_FORMAT
    assert _reloaded(food[4].value) == Decimal("20.00")
    assert _reloaded(food[5].value) == Decimal("83.33")
    assert food[6].value is False

    uncategorized = categories[3]
    assert uncategorized[0].value == "Без категории"
    assert uncategorized[3].value is None
    assert uncategorized[4].value is None
    assert uncategorized[5].value is None


def test_export_summary_sheet_has_money_and_period() -> None:
    file = XlsxReportExporter().export(_sample_report())
    workbook = load_workbook(BytesIO(file.content))
    sheet = workbook["Сводка"]

    assert sheet["A1"].value == "Период с"
    assert _loaded(sheet["B1"].value) == "2026-10-01"
    assert _loaded(sheet["B2"].value) == "2026-10-31"
    assert _reloaded(sheet["B3"].value) == Decimal("2000.00")
    assert _reloaded(sheet["B4"].value) == Decimal("150.00")
    assert _reloaded(sheet["B5"].value) == Decimal("1850.00")
    assert sheet["B3"].number_format == MONEY_CELL_FORMAT

    assert sheet.column_dimensions["A"].width == SUMMARY_WIDTHS[0]
    assert sheet.column_dimensions["B"].width == SUMMARY_WIDTHS[1]


def test_export_empty_period_writes_headers_and_zeroes() -> None:
    file = XlsxReportExporter().export(_empty_report())
    workbook = load_workbook(BytesIO(file.content))

    operations = workbook["Операции"]
    assert operations.max_row == 1
    assert operations.max_column == len(OPERATIONS_HEADERS)
    assert operations["A1"].value == "Дата"

    categories = workbook["По категориям"]
    assert categories.max_row == 1

    summary = workbook["Сводка"]
    assert _reloaded(summary["B3"].value) == Decimal("0.00")
    assert _reloaded(summary["B4"].value) == Decimal("0.00")
    assert _reloaded(summary["B5"].value) == Decimal("0.00")


def test_export_file_has_media_type_and_period_in_filename() -> None:
    file: ExportFile = XlsxReportExporter().export(_sample_report())

    assert file.media_type == XLSX_MEDIA_TYPE
    assert file.filename == "report-2026-10-01_2026-10-31.xlsx"

    empty = XlsxReportExporter().export(_empty_report())
    assert empty.filename == "report-2026-10-25_2026-11-20.xlsx"


def test_export_money_columns_hold_numbers_not_text() -> None:
    """Критерий S7.1: суммы - числовые ячейки с двумя знаками, не текст."""

    file = XlsxReportExporter().export(_sample_report())
    workbook = load_workbook(BytesIO(file.content))

    # «Операции»: Сумма; «По категориям»: Сумма, Лимит, Остаток; «Сводка»: значение.
    money_columns = {
        "Операции": (4,),
        "По категориям": (2, 4, 5),
        "Сводка": (2,),
    }

    for sheet_name, columns in money_columns.items():
        sheet = workbook[sheet_name]
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if cell.column in columns and cell.value is not None:
                    assert not isinstance(cell.value, str), (
                        f"текст вместо числа: {sheet.title}:{cell.coordinate}"
                    )
