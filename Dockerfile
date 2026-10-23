# Tachyon — образ приложения (docs/05: chore/docker-compose, домен R4).
# Сборка: docker build -t tachyon:latest .
# Запуск через docker compose up (см. docker-compose.yml).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости ставятся отдельным слоем, чтобы кэшироваться при изменении кода.
# requirements.txt собран из pyproject.toml (uv pip compile) — воспроизводимая сборка.
COPY requirements.prod.txt ./
RUN pip install --no-cache-dir -r requirements.prod.txt

# Код приложения и миграции.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Каталог для файла БД (монтируется volume'ом).
RUN mkdir -p /app/data

EXPOSE 8000

# Миграции накатываются при старте, затем поднимается uvicorn.
# Порт можно переопределить через переменную PORT.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]