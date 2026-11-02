import os
import tempfile

import pytest

# Point the app at a throwaway database before it is imported.
_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_dir}/test.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import tmdb  # noqa: E402


async def fake_get_movie(movie_id: int) -> dict:
    return {"id": movie_id, "title": f"Movie {movie_id}", "genres": [{"id": 1, "name": "Drama"}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(tmdb, "get_movie", fake_get_movie)
    with TestClient(app) as test_client:
        yield test_client
    SQLModel.metadata.drop_all(engine)
