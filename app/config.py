from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Carga la configuracion desde variables de entorno y, si existe, desde `.env`."""

    database_url: str | None = Field(None, alias="DATABASE_URL")
    pghost: str | None = Field(None, alias="PGHOST")
    pgport: int = Field(5432, alias="PGPORT")
    pguser: str | None = Field(None, alias="PGUSER")
    pgpassword: str | None = Field(None, alias="PGPASSWORD")
    pgdatabase: str | None = Field(None, alias="PGDATABASE")
    rabbitmq_url: str = Field(..., alias="RABBITMQ_URL")
    canvas_api_base_url: str = Field("http://ikusito-canva-api.ikusi", alias="CANVAS_API_BASE_URL")
    mcp_server_url: str = Field("http://ikusito-mcp-server.ikusi/sse", alias="MCP_SERVER_URL")
    canvas_timezone: str = Field("America/Bogota", alias="CANVAS_TIMEZONE")
    mcp_default_logged_user_role: str = Field(
        "gerente_general", alias="MCP_DEFAULT_LOGGED_USER_ROLE"
    )
    refresh_query_concurrency: int = Field(5, alias="REFRESH_QUERY_CONCURRENCY", ge=1, le=20)
    rabbitmq_exchange: str = Field("dashboard.refresh", alias="RABBITMQ_EXCHANGE")
    rabbitmq_routing_key: str = Field("dashboard.refresh.page", alias="RABBITMQ_ROUTING_KEY")
    rabbitmq_queue: str = Field("dashboard.refresh.jobs", alias="RABBITMQ_QUEUE")
    rabbitmq_dlx: str = Field("dashboard.refresh.dlx", alias="RABBITMQ_DLX")
    rabbitmq_dlq: str = Field("dashboard.refresh.jobs.dlq", alias="RABBITMQ_DLQ")
    rabbitmq_prefetch_count: int = Field(5, alias="RABBITMQ_PREFETCH_COUNT", ge=1)
    rabbitmq_max_retries: int = Field(3, alias="RABBITMQ_MAX_RETRIES", ge=0)
    request_timeout_seconds: float = Field(30.0, alias="REQUEST_TIMEOUT_SECONDS", ge=1.0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def build_database_url_from_pg_fields(self) -> Settings:
        """Construye DATABASE_URL desde PG* cuando no se define explicitamente."""

        if self.database_url:
            return self

        missing = [
            name
            for name, value in (
                ("PGHOST", self.pghost),
                ("PGUSER", self.pguser),
                ("PGPASSWORD", self.pgpassword),
                ("PGDATABASE", self.pgdatabase),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Define DATABASE_URL or the complete PG* connection set: "
                + ", ".join(missing)
            )

        user = quote_plus(self.pguser or "")
        password = quote_plus(self.pgpassword or "")
        database = quote_plus(self.pgdatabase or "")
        self.database_url = (
            f"postgresql+asyncpg://{user}:{password}@{self.pghost}:{self.pgport}/{database}"
        )
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings para reutilizar la configuracion."""

    return Settings()
