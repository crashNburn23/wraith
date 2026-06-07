from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime


class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: str = "rss"
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


class SourceOut(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    is_active: bool
    last_fetched_at: Optional[datetime]
    consecutive_failures: int
    last_error: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
