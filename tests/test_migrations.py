import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from danskhjaelp.release import ensure_app_role, run_migrations

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
ROLE = "dh_test"
PASSWORD = "test-password"

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not ADMIN_URL, reason="TEST_DATABASE_URL is not set"),
]


@pytest.fixture
def admin() -> Iterator[Engine]:
    assert ADMIN_URL
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    yield engine
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS role_check"))
    engine.dispose()


def as_app_role() -> Engine:
    assert ADMIN_URL
    return create_engine(make_url(ADMIN_URL).set(username=ROLE, password=PASSWORD))


def test_migrations_enable_pgvector(admin: Engine) -> None:
    assert ADMIN_URL
    run_migrations(ADMIN_URL)
    with admin.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    assert found == 1


def test_app_role_can_use_data_but_not_change_schema(admin: Engine) -> None:
    assert ADMIN_URL
    ensure_app_role(ADMIN_URL, ROLE, PASSWORD)
    ensure_app_role(ADMIN_URL, ROLE, PASSWORD)  # safe to run on every deploy
    with admin.connect() as connection:
        connection.execute(text("CREATE TABLE role_check (id serial PRIMARY KEY, word text)"))

    app = as_app_role()
    with app.begin() as connection:
        connection.execute(text("INSERT INTO role_check (word) VALUES ('stor')"))
        assert connection.execute(text("SELECT word FROM role_check")).scalar_one() == "stor"
    with pytest.raises(ProgrammingError), app.begin() as connection:
        connection.execute(text("DROP TABLE role_check"))
    app.dispose()


def test_app_role_cannot_reach_other_databases(admin: Engine) -> None:
    assert ADMIN_URL
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE IF EXISTS other_env"))
        connection.execute(text("CREATE DATABASE other_env"))
    other_admin = make_url(ADMIN_URL).set(database="other_env")
    ensure_app_role(other_admin.render_as_string(hide_password=False), "dh_other", PASSWORD)

    ensure_app_role(ADMIN_URL, ROLE, PASSWORD)
    app = create_engine(other_admin.set(username=ROLE, password=PASSWORD))
    with pytest.raises(OperationalError), app.connect():
        pass
    app.dispose()
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE other_env"))
