"""Рендеринг диаграммы и дашборда расходов (docs/03 §S10.1 T3).

Jinja2 - деталь представления интерфейсного слоя: домены про шаблоны
ничего не знают, а этот модуль не содержит арифметики денег, только
передачу долей агрегации в шаблон и экранирование HTML (autoescape).

Роутер страницы добавляется задачей TT-33 (``app/interface/api``):
его представление вызовет ``render_category_chart`` /
``render_category_dashboard`` с точками ``ReportingService.by_category``.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Final

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domains.reporting.schemas import SeriesPointDTO
from app.interface.dashboard.chart import TOP_N, ChartData, build_chart

TEMPLATES_DIR: Final = Path(__file__).resolve().parents[1] / "templates"
CHART_TEMPLATE: Final = "reporting/category_chart.html"
DASHBOARD_TEMPLATE: Final = "reporting/category_dashboard.html"

ENVIRONMENT: Final = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(("html",)),
)


def render_category_chart(
    points: Sequence[SeriesPointDTO],
    *,
    date_from: date,
    date_to: date,
    top_n: int = TOP_N,
) -> str:
    """HTML-фрагмент столбчатой диаграммы по точкам домена.

    Каждый вызов строит разметку заново: при смене периода роутером
    диаграмма перестраивается, а не остаётся от прошлого запроса
    (docs/03 §S10.1).
    """

    chart = build_chart(points, top_n=top_n)
    return _render_template(
        CHART_TEMPLATE,
        chart=chart,
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
    )


def render_category_dashboard(
    points: Sequence[SeriesPointDTO],
    *,
    date_from: date,
    date_to: date,
    top_n: int = TOP_N,
) -> str:
    """Полный HTML страницы «Расходы по категориям» с компонентом диаграммы."""

    chart = build_chart(points, top_n=top_n)
    return _render_template(
        DASHBOARD_TEMPLATE,
        chart=chart,
        period_from=date_from.isoformat(),
        period_to=date_to.isoformat(),
    )


def _render_template(
    template_name: str,
    *,
    chart: ChartData,
    period_from: str,
    period_to: str,
) -> str:
    """Заполнить шаблон заранее собранными данными представления.

    Периоды приходят строкой ISO-8601: форматирование дат относится к
    представлению и не дублирует доменную агрегацию.
    """

    return ENVIRONMENT.get_template(template_name).render(
        chart=chart,
        period_from=period_from,
        period_to=period_to,
    )
