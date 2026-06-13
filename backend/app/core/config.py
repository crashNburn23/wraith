from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "sqlite:///./cti.db"

    # LLM
    LLM_PROVIDER: str = "ollama"          # "ollama" | "anthropic"
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_MODEL: str = "qwen2.5:7b"
    ANTHROPIC_API_KEY: Optional[str] = None

    # Embeddings (optional) — served by Ollama at LLM_BASE_URL regardless of
    # LLM_PROVIDER. Empty string disables embeddings entirely.
    # e.g. EMBEDDING_MODEL=nomic-embed-text  (ollama pull nomic-embed-text)
    EMBEDDING_MODEL: str = ""

    # External APIs (all optional)
    NVD_API_KEY: Optional[str] = None

    # Enrichment
    ENRICH_DELAY_SECONDS: float = 0.0

    # Bulletin
    BULLETIN_MAX_ITEMS: int = 30

    # Optional webhook (ntfy-style: plain-text POST) — the daily brief is pushed
    # here after the scheduled bulletin build. Empty disables.
    BRIEF_WEBHOOK_URL: str = ""

    # Scheduler (UTC hours)
    INGEST_HOUR: int = 7
    ENRICH_HOUR: int = 8
    CVE_SYNC_HOUR: int = 9
    BULLETIN_HOUR: int = 10
    SCHEDULER_ENABLED: bool = True

    # Auth
    SECRET_KEY: str = "change-me-in-production-wraith-01"
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = "wraith"

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
