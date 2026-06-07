from sqlalchemy import String, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    sectors: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    threat_actors: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    categories: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
