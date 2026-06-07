from sqlalchemy import String, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, new_uuid


class ScoringConfig(Base, TimestampMixin):
    __tablename__ = "scoring_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Five scoring weights — must sum to 1.0 (validated at API layer)
    weight_ai_severity: Mapped[float] = mapped_column(Float, default=0.35)
    weight_feedback_signal: Mapped[float] = mapped_column(Float, default=0.20)
    weight_profile_match: Mapped[float] = mapped_column(Float, default=0.25)
    weight_kev_bonus: Mapped[float] = mapped_column(Float, default=0.10)
    weight_recency: Mapped[float] = mapped_column(Float, default=0.10)

    # Tuning knobs
    feedback_lookback_days: Mapped[int] = mapped_column(Integer, default=90)
    recency_half_life_days: Mapped[float] = mapped_column(Float, default=3.0)
    min_feedback_articles: Mapped[int] = mapped_column(Integer, default=3)
