"""Shared fixtures: an isolated app (temp database + temp upload folder) per test."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.db.database import Base, get_db, make_engine
from app.main import app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        upload_dir=tmp_path / "uploads",
        max_upload_size_mb=1,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    # No context manager: the real startup hook (which touches the default DB) is skipped.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def upload(client: TestClient):
    """Return a helper: upload(name, content) -> response."""

    def _upload(filename: str, content: bytes, content_type: str = "application/octet-stream"):
        return client.post("/api/files/", files={"file": (filename, content, content_type)})

    return _upload
