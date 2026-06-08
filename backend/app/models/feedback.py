from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, new_uuid


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("article_id", name="uq_feedback_article_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # -1, 0, 1
    reason_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    article = relationship("Article", back_populates="feedback")


class ReadStatus(Base, TimestampMixin):
    __tablename__ = "read_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unread")  # unread / acknowledged / dismissed

    article = relationship("Article", back_populates="read_status")
