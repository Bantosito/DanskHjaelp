import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.db
@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
def test_migrations_enable_pgvector(monkeypatch: pytest.MonkeyPatch) -> None:
    assert DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(DATABASE_URL)
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    engine.dispose()
    assert found == 1
