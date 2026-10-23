"""Дашборд расходов: компонент диаграммы и рендеринг (docs/03 §S10.1).

Данные представления собираются из агрегации TT-26
(``ReportingService.by_category``) и заполняют Jinja2-шаблоны
``app/interface/templates/``. Роутер страницы добавляется задачей TT-33
(``app/interface/api``), здесь только сборка HTML.
"""

from app.interface.dashboard.chart import ChartBar, ChartData, build_chart
from app.interface.dashboard.rendering import (
    render_category_chart,
    render_category_dashboard,
)

__all__ = (
    "ChartBar",
    "ChartData",
    "build_chart",
    "render_category_chart",
    "render_category_dashboard",
)
