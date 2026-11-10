from fastapi.testclient import TestClient

from app.db.session import database_is_ready
from app.main import create_app


def test_live_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_ready_reports_database_without_leaking_the_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.api.v1.health.database_is_ready", lambda engine: False)
    client = TestClient(create_app())
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "unavailable"
    assert "postgresql" not in response.text
    assert "password" not in response.text.lower()


def test_ready_ok_when_database_check_passes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.api.v1.health.database_is_ready", lambda engine: True)
    client = TestClient(create_app())
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


def test_unhandled_error_hides_exception_text() -> None:
    app = create_app()

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("secret database password=super")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "super" not in response.text
    assert "secret" not in response.text


def test_database_is_ready_returns_false_for_a_bad_url() -> None:
    from app.db.session import create_db_engine

    engine = create_db_engine("postgresql+psycopg://invalid:invalid@127.0.0.1:1/none")
    assert database_is_ready(engine) is False
