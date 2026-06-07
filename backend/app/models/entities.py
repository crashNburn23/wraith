from sqlalchemy import String, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, new_uuid


class IOC(Base, TimestampMixin):
    __tablename__ = "iocs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    ioc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ip, domain, hash, url, email
    value: Mapped[str] = mapped_column(Text, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    article = relationship("Article", back_populates="iocs")


class TTPTag(Base, TimestampMixin):
    __tablename__ = "ttp_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(String(20), nullable=False)  # T1566
    technique_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tactic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    article = relationship("Article", back_populates="ttp_tags")


class ThreatActor(Base, TimestampMixin):
    __tablename__ = "threat_actors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)

    article_actors = relationship("ArticleActor", back_populates="actor")


class ArticleActor(Base, TimestampMixin):
    __tablename__ = "article_actors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("threat_actors.id"), nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    article = relationship("Article", back_populates="article_actors")
    actor = relationship("ThreatActor", back_populates="article_actors")

    @property
    def actor_name(self) -> str:
        return self.actor.name if self.actor else "Unknown"


class CVEMention(Base, TimestampMixin):
    __tablename__ = "cve_mentions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("articles.id"), nullable=False)
    cve_id: Mapped[str] = mapped_column(String(20), nullable=False)  # CVE-2024-1234
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    article = relationship("Article", back_populates="cve_mentions")
    record = relationship("CVERecord", primaryjoin="CVEMention.cve_id == foreign(CVERecord.cve_id)", viewonly=True)


class CVERecord(Base, TimestampMixin):
    __tablename__ = "cve_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cve_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    epss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    epss_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_kev: Mapped[bool] = mapped_column(default=False)
    kev_due_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nvd_description: Mapped[str | None] = mapped_column(Text, nullable=True)
