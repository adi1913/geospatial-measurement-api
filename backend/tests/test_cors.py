"""CORS: only configured browser origins may call the API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.db.database import Base, get_db, make_engine
from app.main import create_app
from app.services import file_service

ALLOWED = "http://localhost:5173"
PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}


@pytest.fixture
def cors_client(monkeypatch, tmp_path):
    """A freshly built app (CORS is configured at creation) backed by a temporary database."""
    monkeypatch.setenv("CORS_ORIGINS", f"{ALLOWED}, https://app.example.com")
    get_settings.cache_clear()
    engine = make_engine(f"sqlite:///{(tmp_path / 'cors.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    engine.dispose()
    get_settings.cache_clear()


def test_default_origins_are_local_dev_only_never_wildcard():
    origins = Settings().cors_origin_list

    assert "*" not in origins
    assert origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_preflight_from_allowed_origin_succeeds(cors_client):
    response = cors_client.options("/api/files/", headers={"Origin": ALLOWED, **PREFLIGHT})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]


def test_second_configured_origin_is_allowed_after_trimming(cors_client):
    response = cors_client.options(
        "/api/files/", headers={"Origin": "https://app.example.com", **PREFLIGHT}
    )

    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def test_preflight_from_unknown_origin_is_refused(cors_client):
    response = cors_client.options(
        "/api/files/", headers={"Origin": "https://evil.example", **PREFLIGHT}
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_actual_response_carries_cors_header_only_for_allowed_origin(cors_client):
    allowed = cors_client.get("/api/files/nope/", headers={"Origin": ALLOWED})
    blocked = cors_client.get("/api/files/nope/", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-origin" not in blocked.headers


def test_server_errors_also_carry_cors_headers_so_the_browser_can_read_them(
    cors_client, monkeypatch
):
    """Without this the React app would show a 'network error' instead of a server error."""

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(file_service, "get_file_or_404", explode)

    response = cors_client.get("/api/files/abc/", headers={"Origin": ALLOWED})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
