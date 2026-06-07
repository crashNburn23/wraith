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

    # External APIs (all optional)
    NVD_API_KEY: Optional[str] = None

    # Enrichment
    ENRICH_BATCH_SIZE: int = 5
    ENRICH_DELAY_SECONDS: float = 0.0

    # Scheduler (UTC hours)
    INGEST_HOUR: int = 7
    ENRICH_HOUR: int = 8
    CVE_SYNC_HOUR: int = 9
    BULLETIN_HOUR: int = 10

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
