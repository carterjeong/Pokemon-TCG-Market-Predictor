"""Application settings — Pydantic V2 (pydantic-settings).

Owner: Carter (SWE). Security-sensitive values (JWT secret, AWS Secrets
Manager wiring) are declared here as *placeholders* so the app boots, but
their real sourcing is owned by the security workstream (see app/security/).

All values are read from the environment (or a local `.env` file in dev).
Nothing secret is ever hard-coded.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Pokemon TCG Market Predictor"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    postgres_user: str = "ptcg"
    postgres_password: SecretStr = SecretStr("changeme")  # dev default only
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ptcg_market"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN (asyncpg driver)."""
        dsn = PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )
        return str(dsn)

    # --- pokemontcg.io ingestion (Carter) ---
    pokemontcg_base_url: str = "https://api.pokemontcg.io/v2"
    pokemontcg_api_key: SecretStr | None = Field(
        default=None,
        description="X-Api-Key for pokemontcg.io (raises rate limits).",
    )

    # --- Security placeholders (Owner: CyberSec partner) ---
    # TODO(security): replace static env sourcing with AWS Secrets Manager.
    jwt_secret_key: SecretStr = SecretStr("OVERRIDE-ME-IN-SECRETS-MANAGER")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    """Cached settings factory — inject via `Depends(get_settings)`."""
    return Settings()
