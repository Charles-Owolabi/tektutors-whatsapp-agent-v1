import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "TekTutors WhatsApp AI Sales Agent"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
    PORT: int = int(os.getenv("PORT", 8000))
    
    # Groq Settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    
    # WhatsApp Meta Cloud API
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "tektutors_verify_token_secret")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v20.0"
    
    # Database URL - Supabase / PostgreSQL or local SQLite fallback
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./tektutors.db")
    
    # Email & SMTP Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "admissions@tektutors.com.ng")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "TekTutors Academy")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "True").lower() in ("true", "1", "t")

    # Production & Security Settings
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    WEBHOOK_VERIFY_SIGNATURE_STRICT: bool = os.getenv(
        "WEBHOOK_VERIFY_SIGNATURE_STRICT",
        "False" if os.getenv("APP_ENV", "development") == "development" else "True"
    ).lower() in ("true", "1", "t")
    WORKERS: int = int(os.getenv("WORKERS", 2))

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
