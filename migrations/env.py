import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

if context.config.config_file_name:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)


def run_migrations_online() -> None:
    url = context.config.attributes.get("url") or os.environ["DATABASE_URL"]
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
