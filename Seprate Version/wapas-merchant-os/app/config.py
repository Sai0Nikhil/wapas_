"""Runtime settings, read once from environment / .env."""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    gateway: str = "fake"  # fake | paytm

    paytm_mid: str = ""
    paytm_merchant_key: str = ""
    paytm_host: str = "https://securestage.paytmpayments.com"
    paytm_test_enabled: bool = Field(default=False, validation_alias="PAYTM_TEST_ENABLED")
    paytm_live_enabled: bool = False  # explicit release gate; production money movement stays off by default
    paytm_link_create_path: str = "/link/create"
    paytm_link_fetch_txn_path: str = "/link/fetchTransaction"
    paytm_order_status_path: str = "/v3/order/status"
    # Render assigns this URL at runtime; an explicit PUBLIC_BASE_URL overrides it.
    public_base_url: str = Field(
        default_factory=lambda: os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000",
    )

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # Sarvam only. "off" (default): measured 1-4 s per call and valid JSON on staging. "low"/"high" think first:
    # measured 30-60 s per call, and the thinking sometimes used the whole token budget (empty answer).
    llm_reasoning_effort: str = "off"
    llm_parallel: int = 3                 # cases decided at once, outside the executor lock (Starter: 40 req/min)

    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"

    # Counter image recognition is a separate, explicit integration. It is never
    # inferred from the general-purpose LLM credentials above.
    vision_enabled: bool = Field(default=False, validation_alias="WAPAS_VISION_ENABLED")
    vision_base_url: str = ""
    vision_api_key: str = ""
    vision_model: str = ""

    n8n_webhook_url: str = ""

    telegram_bot_token: str = ""
    telegram_owner_chat_id: str = ""      # owner's phone: approvals, summaries, voice questions
    telegram_customer_chat_id: str = ""   # demo "customer" phone: receives customer messages
    telegram_owner_user_id: str = ""      # needed only if the owner chat is a group: who may press Approve

    # Owner approvals carry an HMAC token bound to the case's current decision and an expiry.
    # Empty = a random secret per run (approval buttons stop working after a restart).
    approval_secret: str = ""
    approval_ttl_hours: float = 12.0      # unanswered approvals close with no customer contact

    paytm_website: str = "WEBSTAGING"

    # WAPAS_ENV is independent of any generic deployment ENV variable. Production
    # is fail-closed; local bootstrap tools require explicit development mode.
    app_env: str = Field(default="production", validation_alias="WAPAS_ENV")

    # The populated installation database is guarded in app.db. Keep this false
    # for routine runs; only the documented, narrowly scoped recovery workflow
    # may temporarily enable it after a verified backup.
    allow_protected_database_writes: bool = Field(
        default=False, validation_alias="WAPAS_ALLOW_PROTECTED_DB_WRITES",
    )

    # Read only for compatibility with older .env files. It is never accepted for auth.
    admin_token: str = ""

    database_url: str = f"sqlite:///{ROOT / 'wapas.db'}"
    merchant_name: str = "Wapas Store"
    reminder_after_seconds: int = 120
    worker_tick_seconds: float = 2.0
    policy_file: str = str(ROOT / "policy.yaml")
    timezone: str = "Asia/Kolkata"
    clock_override: str = ""        # "HH:MM" local time, for demos/tests (quiet hours)
    status_poll_seconds: float = 8.0
    wait_arm_seconds: int = 20         # research "wait" arm delay (simulated customers only)
    agent_delay_seconds: int = 1800    # when the agent recommends "later" on a live case (e.g. just-abandoned checkout)
    learning: bool = True              # research batches only: live customers are never experimented on

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def sarvam_enabled(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def vision_configured(self) -> bool:
        return bool(self.vision_enabled and self.vision_base_url and self.vision_api_key and self.vision_model)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and (self.telegram_owner_chat_id or self.telegram_customer_chat_id))

    @property
    def demo_controls_enabled(self) -> bool:
        return self.app_env.lower() != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
