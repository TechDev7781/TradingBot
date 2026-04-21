from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str
    port: int

    htx_api_key: str | None = None
    htx_api_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_ids: list[str] = []

    @field_validator("telegram_chat_ids", mode="before")
    @classmethod
    def _split_chat_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]

        return [str(value)]


settings = Settings()
