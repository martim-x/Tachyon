import uuid
from datetime import date
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Date, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.main import app
from app.core.persistence.session import get_session

TestBase = declarative_base()

class BudgetLimitTestModel(TestBase):
    __tablename__ = 'budget_limits'
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    category_id = Column(String(36), nullable=False, index=True)
    month = Column(Date, nullable=False)
    limit_amount_cents = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'category_id', 'month', name = 'uq_budget_limit_'
                                                                                 'user_category_month'),)

engine = create_async_engine('sqlite+aiosqlite:///./test_budget.db', echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

@pytest.fixture(scope='function')
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(TestBase.metadata.drop_all)

@pytest.fixture
def client(db):
    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator

    @asynccontextmanager
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()

@pytest.fixture
def ids():
    return str(uuid.uuid4()), str(uuid.uuid4())

@pytest.fixture
def month():
    return date.today()

def test_empty_list(client, ids):
    uid, _ = ids
    r = client.get('/api/v1/budget_limits', params={'user_id': uid})
    assert r.status_code == HTTPStatus.OK and r.json() == []

def test_create_and_conflict(client, ids, month):
    uid, cid = ids
    payload = {'user_id': uid,
               'category_id': cid,
               'month': month.isoformat(),
               'limit_amount_cents': 1000}

    assert (client.post('/api/v1/budget_limits', json=payload).status_code
            == HTTPStatus.CREATED)
    assert (client.post('/api/v1/budget_limits', json=payload).status_code
            == HTTPStatus.CONFLICT)

def test_zero_limit_error(client, ids, month):
    uid, cid = ids
    payload = {'user_id': uid,
               'category_id': cid,
               'month': month.isoformat(),
               'limit_amount_cents': 0}

    assert (client.post('/api/v1/budget_limits', json=payload).status_code
            == HTTPStatus.UNPROCESSABLE_ENTITY)

def test_status_ok(client, ids, month):
    uid, cid = ids
    client.post('/api/v1/budget_limits', json={
        'user_id': uid,
        'category_id': cid,
        'month': month.isoformat(),
        'limit_amount_cents': 500
    })
    r = client.get('/api/v1/budget_limits', params={'user_id': uid})

    assert r.status_code == HTTPStatus.OK
    assert r.json()[0]['status'] == 'OK'

