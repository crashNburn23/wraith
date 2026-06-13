from sqlalchemy import String, Boolean, Text, DateTime, JSON, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, new_uuid


class JobRunRecord(Base, TimestampMixin):
    """Persisted job run state — survives server restarts (replaces in-memory dict)."""
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # ingest | enrich
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running | paused | stopped | completed | error | interrupted
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # full run snapshot (to_dict)


class JobFlag(Base, TimestampMixin):
    """Pause/stop control flags, persisted so they survive restarts."""
    __tablename__ = "job_flags"

    job_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)


class EnrichmentCorrection(Base, TimestampMixin):
    """Analyst corrections to LLM extractions — fed back into the enrichment prompt
    as few-shot 'do not repeat this mistake' examples."""
    __tablename__ = "enrichment_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ioc | ttp | actor | cve
    action: Mapped[str] = mapped_column(String(20), nullable=False)       # deleted | edited | whitelisted
    original_value: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)


class WatchlistItem(Base, TimestampMixin):
    """Pinned actors/CVEs/keywords — matching articles get a relevance boost."""
    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)  # actor | cve | keyword
    value: Mapped[str] = mapped_column(Text, nullable=False)


class SavedSearch(Base, TimestampMixin):
    """Analyst-saved Intel Hub filter with optional alert rule."""
    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Search filter params (subset of /api/search query params)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Minimum severity for an article to trigger an alert (0 = any)
    alert_severity_min: Mapped[float] = mapped_column(Float, default=0.0)
    last_alerted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Running total of articles ever matched
    match_count: Mapped[int] = mapped_column(Integer, default=0)
