"""Идемпотентные демо-данные: python -m scripts.seed.

Создаёт двух пользователей с категориями, операциями за два месяца,
подпиской и превышенным лимитом. Повторный запуск не создаёт дублей:
если демо-пользователи уже есть, скрипт завершается без изменений.
Данные создаются через доменные сервисы/репозитории, деньги — Decimal.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.core.persistence import session_scope
from app.core.user_context import reset_current_user, set_current_user
from app.domains.budget.models import BudgetLimit
from app.domains.identity.repository import UserRepository
from app.domains.identity.service import IdentityService
from app.domains.ledger.schemas import CategoryCreate, OperationCreate
from app.domains.ledger.service import CategoryService, OperationService
from app.domains.scheduling.models import RecurringRule
from app.domains.scheduling.service import RecurringService

DEMO_PASSWORD = "demo-password-123"
DEMO_USERS = (
    ("demo1@tachyon.local", "Анна"),
    ("demo2@tachyon.local", "Борис"),
)


async def _seed_one_user(session, email: str) -> UUID:
    """Создать пользователя и его демо-данные. Возвращает id пользователя."""

    user_repo = UserRepository(session)
    user = await IdentityService(user_repo).register(email=email, password=DEMO_PASSWORD)

    token = set_current_user(user.id)
    try:
        categories = CategoryService(session)
        income = await categories.create(CategoryCreate(name="Зарплата", kind="income"))
        food = await categories.create(CategoryCreate(name="Продукты", kind="expense"))
        transport = await categories.create(CategoryCreate(name="Транспорт", kind="expense"))
        subscriptions = await categories.create(CategoryCreate(name="Подписки", kind="expense"))

        operations = OperationService(session)
        # Доходы: два месяца.
        for d in (date(2026, 10, 5), date(2026, 11, 5)):
            await operations.create(
                OperationCreate(
                    category_id=income.id,
                    amount=Decimal("100000.00"),
                    kind="income",
                    occurred_at=datetime(d.year, d.month, d.day, 9, 0, tzinfo=UTC),
                )
            )
        # Расходы на продукты: 4 операции, превышают лимит 5000 за октябрь.
        for d in (date(2026, 10, 3), date(2026, 10, 17), date(2026, 11, 2), date(2026, 11, 20)):
            await operations.create(
                OperationCreate(
                    category_id=food.id,
                    amount=Decimal("3500.00"),
                    kind="expense",
                    occurred_at=datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC),
                )
            )
        # Транспорт.
        for d in (date(2026, 10, 8), date(2026, 11, 10)):
            await operations.create(
                OperationCreate(
                    category_id=transport.id,
                    amount=Decimal("1200.00"),
                    kind="expense",
                    occurred_at=datetime(d.year, d.month, d.day, 8, 0, tzinfo=UTC),
                )
            )

        # Лимит на продукты за октябрь: 5000, потрачено 7000 -> превышен.
        session.add(
            BudgetLimit(
                user_id=user.id,
                category_id=food.id,
                month=date(2026, 10, 1),
                limit_amount_cents=500000,
            )
        )
        await session.flush()

        # Подписка (повторяющееся правило).
        rule = RecurringRule(
            user_id=user.id,
            category_id=subscriptions.id,
            kind="monthly",
            amount_cents=99000,
            start_date=date(2026, 10, 1),
            next_run_at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
            note="Подписка на сервис",
        )
        await RecurringService(session).create_rule(rule)

        return user.id
    finally:
        reset_current_user(token)


async def _already_seeded(session) -> bool:
    repo = UserRepository(session)
    for email, _ in DEMO_USERS:
        if await repo.get_by_email(email) is not None:
            return True
    return False


def _allowed_to_run() -> bool:
    """Защита от запуска на не-dev БД (Duo review !38)."""

    if "--force" in sys.argv:
        return True

    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env in {"dev", "test", "local", "development"}:
        return True

    return os.environ.get("SEED_DEMO") == "1"


async def main() -> None:
    if not _allowed_to_run():
        print(
            "Отказ: seed содержит публичный демо-пароль и не предназначен для "
            "production/staging. Запустите с APP_ENV=dev|test|local или флагом --force."
        )
        raise SystemExit(2)

    async with session_scope() as session:
        if await _already_seeded(session):
            print("Демо-данные уже есть — повторный запуск пропущен (идемпотентность).")
            return

        for email, _name in DEMO_USERS:
            user_id = await _seed_one_user(session, email)
            print(f"Создан пользователь {email} (id={user_id})")

    print("Готово: 2 пользователя, категории, операции за 2 месяца, лимит и подписка.")


if __name__ == "__main__":
    asyncio.run(main())