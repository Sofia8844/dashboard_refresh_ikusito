from __future__ import annotations

from app.config import Settings


def test_settings_builds_database_url_from_pg_fields() -> None:
    settings = Settings(
        PGHOST="host.docker.internal",
        PGPORT=5432,
        PGUSER="refresh",
        PGPASSWORD="refresh",
        PGDATABASE="refresh",
        RABBITMQ_URL="amqp://guest:guest@localhost/",
    )

    assert (
        settings.database_url
        == "postgresql+asyncpg://refresh:refresh@host.docker.internal:5432/refresh"
    )


def test_database_url_takes_precedence_over_pg_fields() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@db:5432/custom",
        PGHOST="host.docker.internal",
        PGUSER="refresh",
        PGPASSWORD="refresh",
        PGDATABASE="refresh",
        RABBITMQ_URL="amqp://guest:guest@localhost/",
    )

    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/custom"

