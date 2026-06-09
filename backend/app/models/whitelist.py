from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, new_uuid


class IOCWhitelist(Base, TimestampMixin):
    __tablename__ = "ioc_whitelist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    value: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    ioc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
