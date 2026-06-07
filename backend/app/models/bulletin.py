from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, new_uuid


class Bulletin(Base, TimestampMixin):
    __tablename__ = "bulletins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bulletin_date: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # YYYY-MM-DD
    generated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("BulletinItem", back_populates="bulletin", order_by="BulletinItem.rank")


class BulletinItem(Base, TimestampMixin):
    __tablename__ = "bulletin_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bulletin_id: Mapped[str] = mapped_column(String(36), ForeignKey("bulletins.id"), nullable=False)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # Final score
    computed_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Per-component weighted contributions (weight × raw_value)
    score_ai_severity: Mapped[float] = mapped_column(Float, default=0.0)
    score_feedback_signal: Mapped[float] = mapped_column(Float, default=0.0)
    score_profile_match: Mapped[float] = mapped_column(Float, default=0.0)
    score_kev_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    score_recency: Mapped[float] = mapped_column(Float, default=0.0)

    # Raw values before weight multiplication
    raw_ai_severity: Mapped[float] = mapped_column(Float, default=0.0)
    raw_feedback_signal: Mapped[float] = mapped_column(Float, default=0.0)
    raw_profile_match: Mapped[float] = mapped_column(Float, default=0.0)
    raw_kev_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    raw_recency_factor: Mapped[float] = mapped_column(Float, default=0.0)

    # Which past-feedback articles drove the feedback_signal — JSON list of
    # {article_id, title, overlap_reasons[], feedback_rating}
    feedback_signal_articles: Mapped[list | None] = mapped_column(JSON, nullable=True)

    bulletin = relationship("Bulletin", back_populates="items")
    article = relationship("Article", back_populates="bulletin_items")
