from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///./wapas.db"
    public_base_url: str = "http://localhost:8000"

    paytm_mid: str = ""
    paytm_merchant_key: str = ""
    paytm_website: str = "WEBSTAGING"
    paytm_base_url: str = "https://securegw-stage.paytm.in"

    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_model: str = "sarvam-105b"

    telegram_bot_token: str = ""
    telegram_owner_chat_id: str = ""

    approval_signing_secret: str = "change-me"

    auto_limit_inr: int = 5000
    max_reminders: int = 2
    min_confidence: float = 0.7


@lru_cache
def get_settings() -> Settings:
    return Settings()
