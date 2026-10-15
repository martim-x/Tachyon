"""Фабрики: доменные строки с явным user_id, чтобы изоляция была видна в коде теста."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.budget.models import BudgetLimit
from app.domains.identity.models import User
from app.domains.ledger.models import Category, Operation
from app.domains.notification.models import Notification
from app.domains.scheduling.models import RecurringExecution, RecurringRule


async def create_user(session: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="хеш")
    session.add(user)
    await session.flush()
    return user


async def create_category(session: AsyncSession, user_id: UUID, name: str = "Продукты") -> Category:
    category = Category(user_id=user_id, name=name, kind="income")
    session.add(category)
    await session.flush()
    return category


async def create_operation(session: AsyncSession, user_id: UUID) -> Operation:
    category = await create_category(session, user_id, name="Операции")
    operation = Operation(
        user_id=user_id,
        category_id=category.id,
        amount_cents=1000,
        kind="expense",
    )
    session.add(operation)
    await session.flush()
    return operation


async def create_budget_limit(session: AsyncSession, user_id: UUID) -> BudgetLimit:
    category = await create_category(session, user_id, name="Лимиты")
    budget_limit = BudgetLimit(
        user_id=user_id,
        category_id=category.id,
        month=date(2026, 10, 1),
        limit_amount_cents=5000,
    )
    session.add(budget_limit)
    await session.flush()
    return budget_limit


async def create_recurring_rule(session: AsyncSession, user_id: UUID) -> RecurringRule:
    category = await create_category(session, user_id, name="Правила")
    recurring_rule = RecurringRule(
        user_id=user_id,
        category_id=category.id,
        kind="monthly",
        amount_cents=1500,
        start_date=date(2026, 10, 1),
        next_run_at=datetime.now(UTC),
    )
    session.add(recurring_rule)
    await session.flush()
    return recurring_rule


async def create_recurring_execution(session: AsyncSession, user_id: UUID) -> RecurringExecution:
    recurring_rule = await create_recurring_rule(session, user_id)
    recurring_execution = RecurringExecution(
        user_id=user_id,
        rule_id=recurring_rule.id,
        period_date=date(2026, 10, 1),
    )
    session.add(recurring_execution)
    await session.flush()
    return recurring_execution


async def create_notification(session: AsyncSession, user_id: UUID) -> Notification:
    notification = Notification(
        user_id=user_id,
        type="limit_exceeded",
        payload={"month": "2026-10"},
    )
    session.add(notification)
    await session.flush()
    return notification
