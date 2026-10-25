"""Интеграционные тесты HTML-страниц дашборда (docs/03 §S8.1, задача TT-33).

Имена тестов содержат «dashboard» для `pytest -k dashboard`, «isolation»
для `pytest -k isolation` и «empty» для `pytest -k empty` (docs/06
§«Структура тестов»). Фикстуры только из tests/conftest.py.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import (
    ApiClientFactory,
    CategoryFactory,
    LoggedInClient,
    OperationFactory,
)

pytestmark = pytest.mark.integration


async def test_dashboard_page_shows_month_summary_for_logged_user(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """docs/03 §S8.1 T1: сводка месяце — доходы, расходы, остаток и прогноз.

    Часы заморожены на 2026-10-15 (docs/06 §Фикстуры): 150.00 к 15-му числу
    дают прогноз 150 + 150/15 * 16 = 310.00 (кейс AC9 docs/06).
    """
    food = await category_factory(api_client_a.user, name="Продукты", kind="expense")
    salary = await category_factory(api_client_a.user, name="Зарплата", kind="income")

    await operation_factory(
        api_client_a.user,
        Decimal("150.00"),
        category=food,
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("2000.00"),
        category=salary,
        kind="income",
        occurred_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )

    response = await api_client_a.client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    html = response.text
    assert "<!doctype html>" in html.lower()
    for heading in ("Дашборд", "Доходы", "Расходы", "Остаток", "Прогноз", "2026-10"):
        assert heading in html

    assert "2000.00" in html
    assert "150.00" in html
    assert "1850.00" in html
    assert "310.00" in html

    # Компонент диаграммы TT-29 (MR !31) встроен в страницу: тот же период,
    # что у сводки (docs/03 §S10.1); разметка компонента узнаваема.
    assert "Диаграмма расходов по категориям" in html
    assert "период 2026-10-01 — 2026-10-31" in html


async def test_dashboard_page_empty_state_for_user_without_operations(
    api_client_a: LoggedInClient,
) -> None:
    """docs/03 §S8.1: пустой пользователь — подсказка, а не 500 и не ноль.

    Zero-траты — штатное состояние (docs/06 §Нулевые траты): страница
    отдаётся 200 с нулями в сводке и явным пустым состоянием таблицы.
    """
    response = await api_client_a.client.get("/dashboard")

    assert response.status_code == 200
    html = response.text
    assert "Дашборд" in html
    assert "Операций пока нет" in html
    assert "0.00" in html
    # Пустое состояние диаграммы TT-29 тоже отображается (не 500, не тишь).
    assert "Расходов за выбранный период нет" in html


async def test_dashboard_page_isolation_hides_other_user_data(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """docs/03 §S9.2: дашборд показывает только данные своего пользователя.

    Диаграмма и сводка собираются из той же агрегации с фильтром по
    user_id, поэтому чужие суммы и имена категорий в HTML не попадают.
    """
    cat_a = await category_factory(api_client_a.user, name="Продукты Алисы", kind="expense")
    cat_b = await category_factory(api_client_b.user, name="Расходы Боба", kind="expense")

    await operation_factory(
        api_client_a.user,
        Decimal("77.77"),
        category=cat_a,
        occurred_at=datetime(2026, 10, 3, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_b.user,
        Decimal("9999.99"),
        category=cat_b,
        occurred_at=datetime(2026, 10, 3, 12, tzinfo=UTC),
    )

    html_a = (await api_client_a.client.get("/dashboard")).text

    assert "77.77" in html_a
    assert "Продукты Алисы" in html_a
    assert "9999.99" not in html_a
    assert "Расходы Боба" not in html_a

    html_b = (await api_client_b.client.get("/dashboard")).text

    assert "9999.99" in html_b
    assert "77.77" not in html_b


async def test_dashboard_page_accepts_empty_form_values(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """Duo review !29: браузерная форма шлёт все поля, включая пустые строки.

    Незаполненные фильтры это «фильтр не задан», а не 422: страница
    должна отдаться HTML с новой сводкой. Порядок дат при обоих
    непустых значениях по-прежнему валидируется доменной моделью.
    """
    client: AsyncClient = api_client_a.client

    all_empty = await client.get(
        "/dashboard",
        params={"from": "", "to": "", "category_id": "", "type": ""},
    )
    assert all_empty.status_code == 200
    assert "<!doctype html>" in all_empty.text.lower()

    # Страница всё ещё отдаётся, если заполнено только одно поле формы.
    partial = await client.get(
        "/dashboard",
        params={"from": "2026-10-10", "category_id": ""},
    )
    assert partial.status_code == 200

    # Оба заполненных поля валидируются: перевёрнутый период — 422.
    reversed_period = await client.get(
        "/dashboard",
        params={"from": "2026-10-15", "to": "2026-10-10"},
    )
    assert reversed_period.status_code == 422


async def test_dashboard_page_filters_operations_by_period_category_and_foreign_id(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """docs/03 §S8.1 T2: таблица последних операций с фильтрами.

    Фильтры по дате и категории задают страницу через те же параметры
    OperationListQuery, что и GET /api/v1/operations; чужой идентификатор
    категории не протекает в выборку (ScopedRepository).
    """
    food = await category_factory(api_client_a.user, name="Продукты", kind="expense")
    transport = await category_factory(api_client_a.user, name="Транспорт", kind="expense")
    foreign = await category_factory(api_client_b.user, name="Чужая", kind="expense")

    await operation_factory(
        api_client_a.user,
        Decimal("25.50"),
        category=food,
        occurred_at=datetime(2026, 10, 2, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("31.50"),
        category=food,
        occurred_at=datetime(2026, 10, 14, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("90.00"),
        category=transport,
        occurred_at=datetime(2026, 10, 6, 12, tzinfo=UTC),
    )

    client: AsyncClient = api_client_a.client

    by_food = await client.get("/dashboard", params={"category_id": str(food.id)})
    assert by_food.status_code == 200
    html_food = by_food.text
    assert "25.50" in html_food
    assert "31.50" in html_food
    # Диаграмма живёт по периоду, а не по категории (S10.1): «Транспорт 90.00»
    # остаётся в её картинке месяца; фильтр категории действует на таблицу.
    assert "Всего операций за выбранный период: 2" in html_food
    assert "Всего операций за выбранный период: 3" not in html_food

    in_period = await client.get(
        "/dashboard",
        params={"from": "2026-10-10", "to": "2026-10-15"},
    )
    assert in_period.status_code == 200
    html_period = in_period.text
    assert "31.50" in html_period
    assert "25.50" not in html_period
    # Сужение периода убирает 25.50 (2-е) и 90.00 (6-е) из таблицы И диаграммы.
    assert "90.00" not in html_period
    assert "Всего операций за выбранный период: 1" in html_period
    # docs/03 §S10.1: смена периода перестраивает диаграмму.
    assert "период 2026-10-10 — 2026-10-15" in html_period
    assert "период 2026-10-01 — 2026-10-31" not in html_period

    by_foreign = await client.get(
        "/dashboard",
        params={"category_id": str(foreign.id)},
    )
    assert by_foreign.status_code == 200
    assert "Операций пока нет" in by_foreign.text

    reversed_period = await client.get(
        "/dashboard",
        params={"from": "2026-10-15", "to": "2026-10-10"},
    )
    assert reversed_period.status_code == 422


async def test_dashboard_page_requires_authentication(
    api_client: ApiClientFactory,
) -> None:
    """Анонимный браузерный запрос на /dashboard редиректит на /login."""
    client: AsyncClient = api_client()

    response = await client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
