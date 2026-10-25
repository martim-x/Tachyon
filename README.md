# Tachyon — трекер доходов и расходов

Многопользовательское приложение для учёта личных доходов и расходов: категории
и операции, лимиты бюджета с алертами, повторяющиеся операции, прогноз трат до
конца месяца, отчёты с выгрузкой в Excel и PDF.

Реализовано как REST API на FastAPI плюс браузерный дашборд. Архитектура —
модульный монолит с вертикальными доменными срезами, 7 доменов.

![logo](assets/logo.png)

| Параметр | Значение |
|---|---|
| Live-стенд | <https://tachyon-demo.up.railway.app> |
| Swagger | <https://tachyon-demo.up.railway.app/docs> |
| API | 22 пути, 32 операции |
| Тесты | 329 (все зелёные) |
| Код приложения / тестов | 7 480 / 8 658 строк Python |

## Стек

| Слой | Технологии |
|---|---|
| Язык | Python 3.11+ (CI и Docker — 3.12) |
| API | FastAPI, Pydantic v2, python-multipart (формы) |
| Данные | SQLAlchemy 2 (async), SQLite через aiosqlite, Alembic |
| Аутентификация | JWT (PyJWT), bcrypt |
| Аналитика | pandas (агрегации), numpy |
| Экспорт | openpyxl (Excel), reportlab (PDF, шрифт DejaVu для кириллицы) |
| Веб-интерфейс | Jinja2, HTMX (страница уведомлений) |
| Планировщик | APScheduler |
| Тесты и качество | pytest, pytest-asyncio, pytest-cov, httpx, ruff, mypy, bandit |
| Запуск | uvicorn |

Зависимости и версии — в `pyproject.toml`. `requirements.txt` (с `--extra dev`) и
`requirements.prod.txt` собраны из него командой
`uv pip compile pyproject.toml --extra dev --universal`; Dockerfile ставит именно
prod-файл. CI ставит зависимости из `pyproject.toml` через `pip install -e ".[dev]"`,
поэтому оба pinned-файла нужно пересобирать при изменении зависимостей — иначе
сценарий «запуск с нуля» и образ разойдутся с пайплайном.

## Запуск с нуля

Требуется Python 3.11 или новее.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: Copy-Item .env.example .env
alembic upgrade head               # создаёт tachyon.db и таблицы
uvicorn app.main:app --reload
```

После запуска доступны:

- дашборд: <http://127.0.0.1:8000/login> → после входа `/dashboard`;
- health-check: <http://127.0.0.1:8000/health>;
- Swagger: <http://127.0.0.1:8000/docs>;
- ReDoc: <http://127.0.0.1:8000/redoc>.

Без применённых миграций `POST /api/v1/auth/register` отвечает
`INTERNAL_ERROR` — сначала `alembic upgrade head`.

Файл `.env` содержит локальные настройки и секреты, поэтому не добавляется в Git;
шаблон допустимых переменных — `.env.example`.

## Переменные окружения

| Переменная | Обязательна | По умолчанию | Назначение |
|---|---|---|---|
| `DATABASE_URL` | да | — | строка подключения, например `sqlite+aiosqlite:///./tachyon.db` |
| `SECRET_KEY` | да | — | подпись JWT, не короче 32 символов |
| `TOKEN_TTL` | нет | `60` | время жизни access-токена, минуты |
| `APP_NAME` | нет | `Tachyon` | заголовок приложения |
| `LOG_LEVEL` | нет | `INFO` | уровень логирования |
| `SCHEDULER_ENABLED` | нет | `false` | включает APScheduler |
| `SCHEDULER_INTERVAL_SECONDS` | нет | `60` | период опроса правил |
| `COOKIE_SECURE` | нет | `false` | флаг `Secure` у cookie входа; на HTTPS включать |

Переменные окружения имеют приоритет над `.env` (pydantic-settings).

## Демо-данные

```bash
APP_ENV=dev python -m scripts.seed     # или: python -m scripts.seed --force
```

Скрипт создаёт двух пользователей (`demo1@tachyon.local`, `demo2@tachyon.local`),
категории доходов и расходов, операции за два месяца, лимит бюджета и
повторяющееся правило. Запуск идемпотентен: если демо-пользователи уже есть,
скрипт ничего не меняет. Пароль демо-пользователей задан в `scripts/seed.py`.

Защита от прода: без `APP_ENV=dev|test|local`, `SEED_DEMO=1` или флага `--force`
скрипт отказывается работать, потому что содержит публичный демо-пароль.

## Веб-интерфейс

| Страница | Что делает |
|---|---|
| `GET/POST /login` | форма входа, при успехе ставит HttpOnly-cookie `access_token` |
| `GET /logout` | очищает cookie |
| `GET /dashboard` | сводка за период, фильтры, таблица операций, PDF-выгрузка |
| `GET /dashboard/notifications` | лента алертов по лимитам, отметка «прочитано» через HTMX |

Разделение аутентификации сознательное: **API принимает только Bearer-токен**,
cookie работает исключительно на HTML-страницах. Это закрывает CSRF для API:
браузер не приложит токен к запросу автоматически. Неавторизованный браузер
получает `303` на `/login`, неавторизованный API-клиент — `401` с конвертом
ошибки.

Создание и редактирование операций, категорий, лимитов и правил — через API и
Swagger; дашборд работает в режиме чтения.

## API

Полная схема — `openapi.json` (регенерируется из кода и сверяется тестом).

| Домен | Методы и пути |
|---|---|
| identity | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| ledger | `GET/POST /api/v1/operations`, `GET/PATCH/DELETE /api/v1/operations/{operation_id}`, `GET/POST /api/v1/categories`, `GET/PATCH/DELETE /api/v1/categories/{category_id}` |
| budget | `GET/POST /api/v1/budget-limits`, `PUT /api/v1/budget-limits/{category_id}`, `GET /api/v1/budget-limits/status` |
| forecasting | `GET /api/v1/forecast` |
| reporting | `GET /api/v1/reports/monthly`, `GET /api/v1/reports/by-category`, `GET /api/v1/reports/monthly/export` (Excel), `GET /api/v1/reports/monthly/export/pdf` |
| scheduling | `GET/POST /api/v1/recurring/rules`, `GET/PATCH/DELETE /api/v1/recurring/rules/{rule_id}`, `POST /api/v1/recurring/rules/run` |
| notification | `GET /api/v1/notifications`, `PATCH /api/v1/notifications/{notification_id}/read` |
| служебное | `GET /health` |

### Экспорт отчётов

- `GET /api/v1/reports/monthly/export?format=xlsx` — Excel, три листа: «Операции», «По категориям», «Сводка».
- `GET /api/v1/reports/monthly/export/pdf?from=YYYY-MM-DD&to=YYYY-MM-DD` — PDF, один файл, кириллица через встроенный DejaVu. Параметра `format` у PDF-ветки нет; без дат или при `from > to` — `422`.

### Ошибки

Единый конверт `{"error": {"code": "...", "message": "...", "detail": [...]}}`.
Коды машиночитаемые и в верхнем регистре (`NOT_FOUND`, `VALIDATION_ERROR`,
`AUTHENTICATION_FAILED`). Чужой объект отдаёт `404`, а не `403` — существование
чужих записей не подтверждается.

## Архитектура

```
app/
├── core/            # конфиг, ошибки, логирование, Money, Clock, UserContext, события, доступ к данным
├── domains/         # вертикальные срезы: identity, ledger, budget, scheduling,
│                    # forecasting, reporting, notification
│   └── <домен>/     # слои: models.py -> repository.py -> service.py -> api.py
├── interface/       # сборка FastAPI-приложения, страницы, шаблоны
├── infrastructure/  # планировщик, обработчики событий, внешние адаптеры
└── main.py
tests/
├── unit/            # бизнес-логика без БД
├── integration/     # сценарии на временной SQLite
└── e2e/             # сквозные пользовательские сценарии
```

Приложение построено как **модульный монолит с вертикальными доменными срезами**.
Внутри каждого домена выдержаны слои: данные (`models.py`, `repository.py`),
бизнес-логика (`service.py`), интерфейс (`api.py`). Домены владеют собственными
таблицами и зависят друг от друга строго снизу вверх:

```
identity -> ledger -> {budget, scheduling} -> forecasting -> reporting -> export
```

`notification` подписан на доменные события и не знает, из какого домена они
пришли. Ядро (`app/core`) не зависит ни от одного домена.

| Домен | Ответственность |
|---|---|
| `identity` | пользователи, регистрация, вход, JWT |
| `ledger` | операции, категории, фильтры и пагинация |
| `budget` | лимиты на категорию и месяц, пороги 80 % / 100 %, статус |
| `scheduling` | повторяющиеся правила, clamp дат, catch-up, идемпотентность |
| `forecasting` | стратегии темпа трат, прогноз до конца месяца |
| `reporting` | агрегации, DTO, диаграмма, Excel и PDF |
| `notification` | алерты о порогах с дедупликацией |

Расчёты прогноза вынесены в **чистое вычислительное ядро**
`app/domains/forecasting/`: модуль не импортирует SQLAlchemy и FastAPI, поэтому
тестируется без базы данных. Календарная математика берёт длину месяца из
`calendar.monthrange`, а не из `timedelta(days=30)`, поэтому февраль високосного
года считается как 29 дней.

Деньги хранятся целыми копейками (`amount_cents`), расчёты идут в `Decimal` с
округлением `ROUND_HALF_UP`; float в денежных путях не используется. Валюта одна
(рубли) — мультивалютность не поддерживается.

### Изоляция данных

Изоляция обеспечена механизмом, а не дисциплиной:

- у каждой пользовательской таблицы есть `user_id` с индексом;
- `UserContext` (contextvar) — единственный источник текущего пользователя;
- все репозитории наследуют `ScopedRepository`, который берёт `user_id` из
  контекста и не принимает его снаружи;
- query-builder наружу не выдаётся, а пустой контекст приводит к исключению, а
  не к пустой выдаче;
- владение внешними ключами проверяется в репозитории (`_assert_fk_ownership`),
  поэтому чужую категорию нельзя подставить в свою операцию;
- обращение к чужому объекту по id возвращает `404`, а не `403`.

### Границы доменов

Проверяются автоматически в CI (`scripts/check_boundaries.sh`): в `forecasting`
запрещены импорты ORM и HTTP-фреймворка, в `reporting` — `session.commit`,
APScheduler упоминается только в `app/infrastructure/scheduler.py`.

### Схема БД

| Таблица | Что хранит | Колонки |
|---|---|---|
| `users` | пользователи | `id`, `email`, `password_hash`, `token_version`, `created_at` |
| `categories` | категории доходов и расходов | `id`, `user_id`, `name`, `kind`, `color`, `is_default` |
| `operations` | операции | `id`, `user_id`, `category_id`, `amount_cents`, `kind`, `occurred_at`, `note`, `source`, `recurring_execution_id` |
| `budget_limits` | лимит на категорию и месяц | `id`, `user_id`, `category_id`, `month`, `limit_amount_cents` |
| `recurring_rules` | правила повторяющихся операций | `id`, `user_id`, `category_id`, `kind`, `interval`, `amount_cents`, `note`, `start_date`, `end_date`, `next_run_at`, `last_run_at`, `is_active` |
| `recurring_executions` | факты генерации (идемпотентность) | `id`, `user_id`, `rule_id`, `period_date`, `operation_id` |
| `notifications` | уведомления о порогах | `id`, `user_id`, `month`, `type`, `payload`, `is_read`, `created_at` |

Схема накатывается миграциями Alembic (`migrations/versions/`), а не
`create_all`; обратимость (`up → down → up`) проверяется в CI.
`notifications` имеет уникальный индекс по (`user_id`, `month`, `type`) — один
алерт на пользователя, месяц и порог.

## Тесты

```bash
pytest                                                                    # 329 тестов
pytest -m unit                                                            # 97
pytest -m integration                                                     # 196
pytest -m e2e                                                             # 4
pytest -k isolation                                                       # 30
pytest -k forecast                                                        # 43
pytest -k empty                                                           # 27
pytest --cov=app --cov-fail-under=70                                      # покрытие
alembic upgrade head && alembic downgrade base && alembic upgrade head    # обратимость миграций
```

Остальные 32 теста (лимиты и доменные события) идут без маркера и попадают в
полный прогон. Тесты выполняются на временной SQLite: каждый тест получает копию
БД-шаблона с накатанными миграциями и не трогает рабочую базу
(`tests/conftest.py`).

## Линтеры и типы

```bash
ruff check .                                            # стиль и импорты
mypy app                                                # статические типы
bandit -r app -c pyproject.toml -ll -iii                # безопасность
bash scripts/check_boundaries.sh                        # границы доменов
```

`ruff`, `mypy` и `bandit` настроены в `pyproject.toml`; bandit блокирует находки
HIGH/MEDIUM с высокой уверенностью (без `|| true`).

## CI

`.gitlab-ci.yml`, 10 стадий; падение любой из них блокирует merge.

| Стадия | Что проверяет |
|---|---|
| `lint-style` | `ruff check .` |
| `lint-types` | `mypy app` |
| `lint-security` | `bandit -ll -iii` |
| `boundaries` | `scripts/check_boundaries.sh` |
| `test-unit` | `pytest -m unit` |
| `test-integration` | `pytest -m integration` |
| `test-e2e` | `pytest -m e2e` |
| `coverage` | `pytest --cov=app --cov-fail-under=70` |
| `db` | `alembic upgrade → downgrade → upgrade` |
| `docker-build` | `docker build -t app:test .` |

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Стеклок: `python:3.12-slim`, зависимости из `requirements.prod.txt`, миграции
накатываются в `CMD` перед стартом uvicorn. Порт контейнера 8000, наружу
пробрасывается `${APP_PORT:-8000}`. База лежит в `./data` (volume), поэтому
переживает пересоздание контейнера. Секреты в образ не вшиваются — читаются из
`.env` через pydantic-settings.

## Деплой на Railway

Схема: работа и MR — в GitLab, Railway собирает образ из зеркала на GitHub
(`main`). После пуша в GitLab нужен `git push github main`, иначе прод останется
на старом коммите.

Сервис: проект `tachyon-demo`, домен `https://tachyon-demo.up.railway.app`,
приложение слушает порт из `PORT` (Railway задаёт `8080`).

Обязательные переменные: `DATABASE_URL`, `SECRET_KEY` (≥ 32 символов). Для HTTPS
также `COOKIE_SECURE=true`. `.env` на прод не едет — только переменные окружения.

**Volume не подключён:** база живёт в файловой системе контейнера, поэтому каждый
деплой создаёт её заново (Alembic накатывает все миграции с нуля) и демо-данные
нужно заливать повторно через `scripts/seed.py`.

## Что осталось за рамками

| Чего нет | Комментарий |
|---|---|
| Внешняя доставка уведомлений | порт `Notifier` объявлен, реализация — `NullNotifier`: алерты видны только в API и дашборде, email/Telegram/push не отправляются |
| Импорт банковских выписок | операции вводятся через API или Swagger |
| Общие аккаунты (семья, команда) | изоляция строгая: один пользователь — один кошелёк |
| Смена и сброс пароля | есть только регистрация и вход |
| Выход со всех устройств | поле `token_version` заведено, но эндпоинта нет |
| Редактирование данных в браузере | дашборд только читает, запись через API |
| Мультивалютность | одна валюта, суммы без кода валюты |

## Что здесь лежит

| Файл | О чём |
|---|---|
| `docs/00_интерфейс_документации.md` | Карта файлов, маршрут чтения по ролям, гейт перед кодом, реестр открытых решений |
| `docs/01_задание_и_критерии.md` | Что делаем, что оценивается, обязательные требования |
| `docs/02_архитектура.md` | Почему модульный монолит, домены, слои, структура папок |
| `docs/03_бэклог_и_оценки.md` | Epic → Story → Task со story points, приоритеты и лестница сокращений |
| `docs/04_команда_и_роли.md` | 5 ролей, матрица пересечения, Scrum-цикл |
| `docs/05_процесс_разработки.md` | Git, Pull Request, code review, CI, Definition of Done |
| `docs/06_тестирование.md` | Что тестировать и почему именно это оценивают |
| `docs/07_защита_проекта.md` | Чек-лист демо, вероятные вопросы комиссии |
| `docs/08_перечень_задач.md` | Недельный чек-лист и критический путь |
| `scripts/seed.py` | идемпотентные демо-данные |
| `scripts/check_boundaries.sh` | проверка границ доменов для CI |
| `openapi.json` | экспортированная схема API, сверяется тестом |
| `assets/logo.png` | логотип проекта |

Сроки проекта: сдача кода — 22 октября, защита — 24–25 октября.

## Разработка

```bash
pip install pre-commit
pre-commit install
```

Команда: 5 человек, распределение ролей и зон ответственности — в
`docs/04_команда_и_роли.md`.

Документы в `docs/` описывают один и тот же проект: при изменении бэклога
правьте оценки в `03`, приоритеты в `04`, критерии приёмки в `06`.
