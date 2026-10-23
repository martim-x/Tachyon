"""PDF-экспорт отчёта (docs/02 §export, docs/03 §S7.2).

Адаптер формата: данные приходят уже агрегированными из reporting
(ReportDTO от ReportingService), pandas-логика здесь не дублируется
(NFR-3). Деньги рендерятся строками с двумя знаками: Decimal.quantize
("0.01"), без float в любом виде.

Кириллица: шрифт DejaVu Sans встраивается в файл (assets/fonts),
поэтому заголовки открываются без квадратов. Числа и суммы - base-14
Helvetica (ASCII), сумма остаётся точным строковым значением из Decimal.
"""

import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from app.domains.reporting.schemas import ReportDTO

_FONT_NAME = "DejaVu"
_FONT_NAME_BOLD = "DejaVu-Bold"

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Резервные системные пути, если assets/fonts не лежит рядом с кодом
# (например, при установке пакета из wheel): первый найденный файл
# регистрируется, иначе base-14 Helvetica - файл остаётся валидным PDF,
# кириллица же в этом случае зависит от подстановки просмотрщика.
_FONT_CANDIDATES = (
    _REPO_ROOT / "assets" / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/opt/local/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/opt/homebrew/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)

_BOLD_FONT_CANDIDATES = (
    _REPO_ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/opt/local/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    Path("/opt/homebrew/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    Path("/Library/Fonts/Arial Bold.ttf"),
)

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.01")


def _escape_markup(text: str) -> str:
    """Экранировать & < > для Paragraph (он разбирает вход как разметку).

    Ручная замена вместо xml.sax.saxutils.escape: saxutils попадает в
    bandit-чёрный список парсеров XML (B406), хотя здесь только строки.
    """

    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _register_cyrillic_font(candidates: tuple[Path, ...], font_name: str) -> str:
    """Зарегистрировать кириллический шрифт один раз за процесс.

    Возвращает имя зарегистрированного шрифта; если ни один файл не
    найден, отдаёт base-14 Helvetica.
    """

    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name

    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
            return font_name

    return "Helvetica"


_FONT = _register_cyrillic_font(_FONT_CANDIDATES, _FONT_NAME)
_FONT_BOLD = _register_cyrillic_font(_BOLD_FONT_CANDIDATES, _FONT_NAME_BOLD)


def format_money(amount: Decimal) -> str:
    """Сумма строкой с двумя знаками из Decimal.quantize("0.01").

    Float-значения отвергаются: представление float не даёт точной
    копейки, а Money и агрегация reporting уже работают на Decimal.
    """

    if not isinstance(amount, Decimal) or isinstance(amount, bool):
        raise TypeError("Деньги в PDF рендерятся только из Decimal")

    return str(amount.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def format_percent(amount: Decimal) -> str:
    """Процент строкой с двумя знаками, без float."""

    if not isinstance(amount, Decimal) or isinstance(amount, bool):
        raise TypeError("Проценты в PDF рендерятся только из Decimal")

    return str(amount.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP))


def report_file_name(date_from: date, date_to: date) -> str:
    """Имя файла с периодом, чтобы отчёты не перетирали друг друга."""

    return f"report-{date_from:%Y%m%d}-{date_to:%Y%m%d}.pdf"


def _title_style() -> ParagraphStyle:
    return ParagraphStyle(
        name="ReportTitle",
        fontName=_FONT_BOLD,
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )


def _period_style() -> ParagraphStyle:
    return ParagraphStyle(
        name="ReportPeriod",
        fontName=_FONT,
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )


def _category_name_style() -> ParagraphStyle:
    """Стиль названий категорий: перенос длинных строк внутри ячейки.

    reportlab не переносит plain-string ячейки, поэтому свободный текст
    пользователя рисуется Paragraph-ом: даже имя на 100 символов
    переносится и не наезжает на соседнюю колонку.
    """

    return ParagraphStyle(
        name="CategoryName",
        fontName=_FONT,
        fontSize=9,
        leading=11,
    )


def _table_style() -> TableStyle:
    """Сетка: шапка и колонка имён - кириллица, числа данных - Helvetica."""

    return TableStyle(
        [
            # 1. Базовый шрифт таблицы: кириллица (шапка и названия).
            ("FONTNAME", (0, 0), (-1, -1), _FONT),
            # 2. Ячейки данных числовых колонок - точные ASCII-строки.
            ("FONTNAME", (1, 1), (-1, -1), "Helvetica"),
            # 3. Строка шапки целиком: кириллица жирным.
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9A9A9A")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
    )


def _summary_rows(report: ReportDTO) -> list[list[str]]:
    """Строки сводки: показатели - кириллицей, суммы - строками Decimal."""

    return [
        ["Показатель", "Сумма"],
        ["Доходы", format_money(report.income)],
        ["Расходы", format_money(report.expense)],
        ["Баланс", format_money(report.balance)],
        [
            f"Прогноз расходов на {report.forecast_month}",
            format_money(report.forecast),
        ],
    ]


def _category_rows(report: ReportDTO) -> list[list[Any]]:
    """Строки таблицы категорий; суммы и доли - строки Decimal.

    Название категории свободное, поэтому рисуется Paragraph-ом с
    переносом и экранированием (Paragraph разбирает вход как разметку,
    имя вида "A & B" иначе исказило бы рендер). Числовые ячейки -
    plain-строки: точные значения из Decimal. Категория без лимита
    даёт пустые ячейки вместо прочерков: значение отсутствует,
    а не равно нулю.
    """

    header = [
        "Категория",
        "Расходы",
        "Доля, %",
        "Лимит",
        "Остаток",
        "Лимит, %",
    ]
    rows: list[list[Any]] = [header]

    for category in report.categories:
        limit_text = "" if category.limit is None else format_money(category.limit)
        remaining_text = (
            "" if category.limit_remaining is None else format_money(category.limit_remaining)
        )
        limit_percent_text = (
            ""
            if category.limit_percent is None
            else format_percent(category.limit_percent)
        )
        rows.append(
            [
                Paragraph(
                    _escape_markup(category.category_name),
                    _category_name_style(),
                ),
                format_money(category.amount),
                format_percent(category.share_percent),
                limit_text,
                remaining_text,
                limit_percent_text,
            ]
        )

    return rows


def _uncompressed_canvas(*args: Any, **kwargs: Any) -> Canvas:
    """Canvas без компрессии контента: суммы читаются из файла напрямую."""

    # doc-template передаёт pageCompression=None, поэтому не setdefault,
    # а явное присваивание: компрессия контента выключена всегда.
    kwargs["pageCompression"] = 0
    return Canvas(*args, **kwargs)


def build_pdf_report(report: ReportDTO) -> bytes:
    """Собрать PDF отчёта с теми же данными, что и Excel (docs/03 §S7.2).

    LongTable переносит категорийную таблицу на следующие страницы,
    повторяя шапку (repeatRows=1), поэтому длинный период не даёт
    «наезда» строк друг на друга.
    """

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Финансовый отчёт {report.date_from:%d.%m.%Y} - {report.date_to:%d.%m.%Y}",
        author="Tachyon",
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    story: list[Flowable] = [
        Paragraph("Финансовый отчёт", _title_style()),
        Paragraph(
            f"Период: {report.date_from:%d.%m.%Y} - {report.date_to:%d.%m.%Y}",
            _period_style(),
        ),
        LongTable(
            _summary_rows(report),
            hAlign="LEFT",
            colWidths=[70 * mm, 40 * mm],
            style=_table_style(),
        ),
        Spacer(1, 8 * mm),
        LongTable(
            _category_rows(report),
            hAlign="LEFT",
            repeatRows=1,
            colWidths=[45 * mm, 25 * mm, 20 * mm, 25 * mm, 25 * mm, 20 * mm],
            style=_table_style(),
        ),
    ]

    document.build(story, canvasmaker=_uncompressed_canvas)
    return buffer.getvalue()


__all__ = [
    "build_pdf_report",
    "format_money",
    "format_percent",
    "report_file_name",
]
