import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


def _sanitize_placeholder_env_vars() -> None:
    """Strip unresolved shell/deployment placeholders before Pydantic validates env values."""
    placeholder_names = [
        "PORT", "WORKERS", "SMTP_PORT", "DEBUG", "SMTP_USE_TLS",
        "WEBHOOK_VERIFY_SIGNATURE_STRICT", "DATABASE_URL", "APP_ENV",
        "GROQ_API_KEY", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "SMTP_HOST",
        "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_FROM_NAME"
    ]
    for name in placeholder_names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip().strip('"').strip("'")
        if cleaned.startswith("$") or cleaned.startswith("${{") or "Postgres.DATABASE_URL" in cleaned:
            os.environ.pop(name, None)


_sanitize_placeholder_env_vars()


def _safe_int_env(name: str, default: int) -> int:
    """Ignore shell placeholders like '$PORT' and invalid values; use the default instead."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return int(default)
    value = raw.strip().strip('"').strip("'")
    if value.startswith("$"):
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_bool_env(name: str, default: bool) -> bool:
    """Parse boolean settings safely for deployment platforms that leave placeholder values."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().strip('"').strip("'")
    if value.startswith("$"):
        return default
    return value.lower() in ("true", "1", "t", "yes", "y", "on")


def _clean_database_url(value: str | None) -> str:
    """Fallback to local SQLite if a deployment platform leaves a placeholder string."""
    candidate = (value or "").strip()
    if not candidate or candidate.startswith("${{") or "Postgres.DATABASE_URL" in candidate or "DATABASE_URL}}" in candidate:
        return "sqlite+aiosqlite:///./tektutors.db"
    return candidate


class Settings(BaseSettings):
    APP_NAME: str = "TekTutors WhatsApp AI Sales Agent"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    DEBUG: bool = _safe_bool_env("DEBUG", APP_ENV.lower() != "production")
    PORT: int = _safe_int_env("PORT", 8000)
    
    # Groq Settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    
    # WhatsApp Meta Cloud API
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "tektutors_verify_token_secret")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v20.0"
    
    # Database URL - Supabase / PostgreSQL or local SQLite fallback
    DATABASE_URL: str = _clean_database_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./tektutors.db"))
    
    # Email & SMTP Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = _safe_int_env("SMTP_PORT", 587)
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "admissions@tektutors.com.ng")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "TekTutors Academy")
    SMTP_USE_TLS: bool = _safe_bool_env("SMTP_USE_TLS", True)

    # Production & Security Settings
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    WEBHOOK_VERIFY_SIGNATURE_STRICT: bool = _safe_bool_env(
        "WEBHOOK_VERIFY_SIGNATURE_STRICT",
        os.getenv("APP_ENV", "development") != "development",
    )
    WORKERS: int = _safe_int_env("WORKERS", 1)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def allowed_origins_list(self) -> list:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = {"case_sensitive": True}

settings = Settings()
