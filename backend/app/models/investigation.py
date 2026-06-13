from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, new_uuid


class Investigation(Base, TimestampMixin):
    """Analyst case / workspace — a named collection of articles with notes."""
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open | closed

    articles = relationship("InvestigationArticle", back_populates="investigation", cascade="all, delete-orphan")
    notes = relationship("InvestigationNote", back_populates="investigation", cascade="all, delete-orphan", order_by="InvestigationNote.created_at")


class InvestigationArticle(Base, TimestampMixin):
    """Article pinned to an investigation, with an optional analyst note."""
    __tablename__ = "investigation_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    investigation_id: Mapped[str] = mapped_column(String(36), ForeignKey("investigations.id"), nullable=False)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    investigation = relationship("Investigation", back_populates="articles")
    article = relationship("Article")


class InvestigationNote(Base, TimestampMixin):
    """Free-text analyst note attached to an investigation."""
    __tablename__ = "investigation_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    investigation_id: Mapped[str] = mapped_column(String(36), ForeignKey("investigations.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    investigation = relationship("Investigation", back_populates="notes")
