"""Run once per deploy: set up the database role, migrate, and register the webhook."""

import asyncio

from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Connection, create_engine, text
from telegram import Bot, Update

from danskhjaelp.config import Settings

# Terraform seeds Key Vault with this until the real token is set by hand.
PLACEHOLDER_TOKEN_PREFIX = "0:"


def _execute(connection: Connection, statement: sql.Composed) -> None:
    connection.exec_driver_sql(statement.as_string(None))


def ensure_app_role(admin_url: str, role: str, password: str) -> None:
    """Give the app its own login, limited to reading and writing data in this one database.

    Dev and prod share a server and roles are server-wide, so CONNECT is also revoked from
    PUBLIC. Otherwise the dev role could connect to the prod database.
    """
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    role_id = sql.Identifier(role)
    with engine.connect() as connection:
        database = sql.Identifier(
            connection.execute(text("SELECT current_database()")).scalar_one()
        )
        exists = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
        ).scalar()
        if not exists:
            _execute(connection, sql.SQL("CREATE ROLE {}").format(role_id))
        _execute(
            connection,
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(role_id, sql.Literal(password)),
        )
        for template in (
            "REVOKE CONNECT ON DATABASE {database} FROM PUBLIC",
            "GRANT CONNECT ON DATABASE {database} TO {role}",
            "GRANT USAGE ON SCHEMA public TO {role}",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}",
        ):
            _execute(connection, sql.SQL(template).format(database=database, role=role_id))
    engine.dispose()


def run_migrations(url: str) -> None:
    config = Config("alembic.ini")
    config.attributes["url"] = url
    command.upgrade(config, "head")


async def register_webhook(settings: Settings) -> None:
    if settings.telegram_bot_token.startswith(PLACEHOLDER_TOKEN_PREFIX):
        print("Telegram token not set yet, skipping webhook registration")
        return
    if not settings.public_url:
        raise SystemExit("PUBLIC_URL is required to register the Telegram webhook")
    async with Bot(settings.telegram_bot_token) as bot:
        await bot.set_webhook(
            url=f"{settings.public_url.rstrip('/')}/telegram/webhook",
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
        )


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    if not (settings.database_admin_url and settings.app_db_role and settings.app_db_password):
        raise SystemExit("DATABASE_ADMIN_URL, APP_DB_ROLE and APP_DB_PASSWORD are required")
    ensure_app_role(settings.database_admin_url, settings.app_db_role, settings.app_db_password)
    run_migrations(settings.database_admin_url)
    asyncio.run(register_webhook(settings))


if __name__ == "__main__":
    main()
