import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.interface.api.app import create_app
from app.main import app

pytestmark = pytest.mark.integration


client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unhandled_error_does_not_expose_traceback() -> None:
    test_app: FastAPI = create_app()

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive internal information")

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "sensitive internal information" not in response.text
