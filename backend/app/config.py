from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    bot_token: str = ""
    bot_username: str = ""
    database_url: str = "postgresql+psycopg://kto:kto@localhost:5432/kto_so_mnoy"
    max_api_url: str = "https://platform-api2.max.ru"
    dev_mode: bool = False
    init_data_ttl: int = 86400
    admin_key: str = ""
    bot_quick_actions: bool = False
    public_url: str = ""
    webhook_secret: str = ""


settings = Settings()
