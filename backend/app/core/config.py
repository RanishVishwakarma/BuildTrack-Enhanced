from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default="BuildTrack API", validation_alias="APP_NAME")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    debug: bool = Field(default=True, validation_alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")

    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGODB_URL",
    )
    mongodb_db_name: str = Field(
        default="buildtrack",
        validation_alias="MONGODB_DB_NAME",
    )

    jwt_secret_key: str = Field(
        default="change-this-secret-before-production",
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # Outgoing email (notifications, password reset). Unset = email disabled.
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, validation_alias="SMTP_FROM_EMAIL")

    # Local development only: include the password-reset token in the API
    # response instead of emailing it. Never enable on a shared deployment -
    # anyone could reset anyone's password. Ignored when APP_ENV=production.
    password_reset_return_token: bool = Field(default=False, validation_alias="PASSWORD_RESET_RETURN_TOKEN")

    # --- Your company's GSTIN: decides CGST+SGST (same state as the vendor)
    # or IGST (different state) on purchase orders. Empty = split not worked out.
    company_gstin: str | None = Field(default=None, validation_alias="COMPANY_GSTIN")

    # --- AI (Anthropic Claude). Unset key = AI features report "not configured".
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    # Which engine answers Site Assistant chat questions:
    #   quick     - free, offline keyword answers from records (no AI model)
    #   ollama    - free local model on this machine rephrases those answers
    #   anthropic - Claude (paid; also needs AI_ENABLED=true and a key)
    ai_provider: str = Field(default="quick", validation_alias="AI_PROVIDER")
    ollama_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_URL")
    ollama_model: str = Field(default="gemma2:2b", validation_alias="OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(default=120.0, validation_alias="OLLAMA_TIMEOUT_SECONDS")
    # Master switch: false guarantees no paid AI calls even if a key is present.
    ai_enabled: bool = Field(default=True, validation_alias="AI_ENABLED")
    # Needed only for API keys that are not scoped to a workspace.
    anthropic_workspace_id: str | None = Field(default=None, validation_alias="ANTHROPIC_WORKSPACE_ID")
    ai_model: str = Field(default="claude-opus-5-5", validation_alias="AI_MODEL")
    ai_effort: str = Field(default="medium", validation_alias="AI_EFFORT")
    ai_max_tool_rounds: int = Field(default=8, validation_alias="AI_MAX_TOOL_ROUNDS")
    ai_requests_per_hour: int = Field(default=60, validation_alias="AI_REQUESTS_PER_HOUR")
    ai_timeout_seconds: float = Field(default=90.0, validation_alias="AI_TIMEOUT_SECONDS")

    # --- Background monitoring (Phase 3).
    monitoring_enabled: bool = Field(default=True, validation_alias="MONITORING_ENABLED")
    monitoring_interval_minutes: int = Field(default=15, validation_alias="MONITORING_INTERVAL_MINUTES")
    escalation_after_minutes: int = Field(default=120, validation_alias="ESCALATION_AFTER_MINUTES")

    # --- Private file storage for progress evidence (Phase 6).
    private_upload_dir: str = Field(default="private_uploads", validation_alias="PRIVATE_UPLOAD_DIR")
    evidence_max_bytes: int = Field(default=10 * 1024 * 1024, validation_alias="EVIDENCE_MAX_BYTES")
    download_link_seconds: int = Field(default=300, validation_alias="DOWNLOAD_LINK_SECONDS")

    # --- Automated voice calls (Phase 8). Off unless every value is set.
    voice_calls_enabled: bool = Field(default=False, validation_alias="VOICE_CALLS_ENABLED")
    twilio_account_sid: str | None = Field(default=None, validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, validation_alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, validation_alias="TWILIO_FROM_NUMBER")
    public_base_url: str | None = Field(default=None, validation_alias="PUBLIC_BASE_URL")
    voice_call_hours: str = Field(default="08:00-20:00", validation_alias="VOICE_CALL_HOURS")
    voice_call_timezone: str = Field(default="Asia/Kolkata", validation_alias="VOICE_CALL_TIMEZONE")
    voice_max_attempts: int = Field(default=2, validation_alias="VOICE_MAX_ATTEMPTS")

    backend_cors_origins: str = Field(
        default="http://localhost:4200,http://127.0.0.1:4200",
        validation_alias="BACKEND_CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # An empty environment variable falls back to the .env value instead
        # of blanking it.
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("company_gstin", "anthropic_api_key", "anthropic_workspace_id", "twilio_account_sid", "twilio_auth_token", "twilio_from_number", "public_base_url", "smtp_host", mode="before")
    @classmethod
    def blank_is_unset(cls, value):
        """Treat empty or whitespace-only secrets as not configured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("api_v1_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            return f"/{value}"
        return value.rstrip("/") or "/api/v1"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env.lower() != "production":
            return self

        if self.debug:
            raise ValueError("APP_DEBUG must be false when APP_ENV=production")
        if self.jwt_secret_key == "change-this-secret-before-production":
            raise ValueError("JWT_SECRET_KEY must be supplied when APP_ENV=production")
        if "*" in self.cors_origins:
            raise ValueError("BACKEND_CORS_ORIGINS must not allow '*' in production")

        return self

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
