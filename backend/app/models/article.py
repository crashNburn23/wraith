from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, new_uuid


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Enrichment lifecycle
    enrichment_status: Mapped[str] = mapped_column(String(50), default="pending")
    enriched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Feed-extracted metadata
    og_image: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM-extracted fields
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    threat_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_severity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    geo_origin: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geo_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Relationships
    source = relationship("Source", back_populates="articles")
    iocs = relationship("IOC", back_populates="article", cascade="all, delete-orphan")
    ttp_tags = relationship("TTPTag", back_populates="article", cascade="all, delete-orphan")
    article_actors = relationship("ArticleActor", back_populates="article", cascade="all, delete-orphan")
    cve_mentions = relationship("CVEMention", back_populates="article", cascade="all, delete-orphan")
    bulletin_items = relationship("BulletinItem", back_populates="article", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="article", cascade="all, delete-orphan")
    read_status = relationship("ReadStatus", back_populates="article", uselist=False, cascade="all, delete-orphan")
